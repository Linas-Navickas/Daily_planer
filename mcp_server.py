"""Small stateless Streamable HTTP MCP server for the planner's ChatGPT plugin."""

from datetime import date, time
from contextlib import contextmanager
from hashlib import sha256
from html import escape
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse, parse_qsl
import base64
import hmac
import json
import math
import secrets
import sqlite3
import time as clock


READ_SCOPE = "planner:read"
WRITE_SCOPE = "planner:write"
TOKEN_TTL = 60 * 60 * 24 * 30
SUPPORTED_PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
CATEGORIES = {"Darbas", "Asmeniniai", "Sveikata", "Kita"}
MCP_LOGIN_ATTEMPTS = {}


class PlannerMCPMixin:
    """MCP and OAuth endpoints mixed into the planner's existing HTTP handler."""

    def mcp_origin(self):
        host = self.headers.get("Host", "localhost:8000")
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "").split(",", 1)[0].strip().lower()
        if forwarded_proto in ("http", "https"):
            scheme = forwarded_proto
        elif host.startswith(("localhost", "127.0.0.1", "[::1]")):
            scheme = "http"
        else:
            scheme = "https"
        return f"{scheme}://{host}"

    def mcp_json(self, status, payload, headers=None):
        body = b"" if status == 202 else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if headers:
            for name, value in headers.items():
                self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def mcp_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def mcp_read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32_768:
                return None
            return self.rfile.read(length)
        except (ValueError, OSError):
            return None

    @contextmanager
    def mcp_db(self):
        db = sqlite3.connect(self.DB_PATH)
        try:
            with db:
                yield db
        finally:
            db.close()

    def mcp_metadata(self, path):
        origin = self.mcp_origin()
        if path == "/.well-known/oauth-protected-resource":
            return {
                "resource": origin + "/mcp",
                "authorization_servers": [origin],
                "scopes_supported": [READ_SCOPE, WRITE_SCOPE],
                "bearer_methods_supported": ["header"],
            }
        if path == "/.well-known/oauth-authorization-server":
            return {
                "issuer": origin,
                "authorization_endpoint": origin + "/authorize",
                "token_endpoint": origin + "/token",
                "registration_endpoint": origin + "/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
                "scopes_supported": [READ_SCOPE, WRITE_SCOPE],
                "client_id_metadata_document_supported": False,
            }
        return None

    def handle_mcp_get(self, parsed):
        metadata = self.mcp_metadata(parsed.path)
        if metadata is not None:
            self.mcp_json(200, metadata)
            return True
        if parsed.path == "/authorize":
            query = parse_qs(parsed.query, keep_blank_values=True)
            fields = {
                key: query.get(key, [""])[0]
                for key in ("client_id", "redirect_uri", "response_type", "state", "code_challenge", "code_challenge_method", "resource", "scope")
            }
            if not self.mcp_valid_authorization_request(fields):
                self.mcp_html(400, "<h1>Neteisinga ChatGPT autorizacijos užklausa</h1>")
                return True
            hidden = "".join(
                f'<input type="hidden" name="{escape(key)}" value="{escape(value)}">'
                for key, value in fields.items()
            )
            page = (
                '<!doctype html><html lang="lt"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Prijungti planuoklį</title><style>body{font:16px system-ui;background:#f5f5f2;color:#242722;max-width:440px;margin:12vh auto;padding:24px}'
                'form{background:#fff;border:1px solid #e7e9e3;border-radius:16px;padding:24px}input[type=password]{box-sizing:border-box;width:100%;height:44px;margin:14px 0;border:1px solid #ccc;border-radius:8px;padding:8px;font:inherit}'
                'button{height:44px;border:0;border-radius:8px;background:#294a38;color:white;padding:0 16px;font:inherit;font-weight:600}.note{color:#666;font-size:14px}</style>'
                '<h1>Prijungti planuoklį prie ChatGPT</h1><p class="note">Patvirtink prieigą prie savo planuoklio. Skaitymo ir įrašymo veiksmai bus leidžiami pagal pažymėtas teises.</p>'
                '<form method="post" action="/authorize">' + hidden
                + '<label for="password">Planuoklio slaptažodis</label><input id="password" name="password" type="password" autocomplete="current-password" required>'
                '<label><input type="checkbox" name="approve" value="yes" required> Leidžiu ChatGPT skaityti ir įrašyti planuoklio duomenis</label><p>'
                '<button type="submit">Prijungti</button></p></form></html>'
            )
            self.mcp_html(200, page)
            return True
        if parsed.path == "/mcp":
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        return False

    def mcp_valid_authorization_request(self, fields):
        if fields["response_type"] != "code" or fields["code_challenge_method"] != "S256":
            return False
        if not all(fields[key] for key in ("client_id", "redirect_uri", "state", "code_challenge", "resource")):
            return False
        try:
            parsed = urlparse(fields["redirect_uri"])
            if parsed.scheme != "https" or parsed.hostname != "chatgpt.com":
                return False
            if len(fields["code_challenge"]) > 128 or len(fields["state"]) > 512:
                return False
            if fields["resource"] != self.mcp_origin() + "/mcp":
                return False
            with self.mcp_db() as db:
                row = db.execute("SELECT redirect_uris FROM oauth_clients WHERE client_id=?", (fields["client_id"],)).fetchone()
            return bool(row and fields["redirect_uri"] in json.loads(row[0]))
        except (ValueError, TypeError, sqlite3.Error):
            return False

    def handle_mcp_post(self, parsed):
        if parsed.path == "/register":
            return self.mcp_register_client()
        if parsed.path == "/authorize":
            return self.mcp_authorize()
        if parsed.path == "/token":
            return self.mcp_token()
        if parsed.path == "/mcp":
            return self.mcp_rpc()
        return False

    def mcp_register_client(self):
        raw = self.mcp_read_body()
        try:
            payload = json.loads(raw or b"")
            redirects = payload.get("redirect_uris")
            if not isinstance(redirects, list) or not redirects:
                raise ValueError
            for uri in redirects:
                parsed = urlparse(uri)
                if parsed.scheme != "https" or parsed.hostname != "chatgpt.com":
                    raise ValueError
            client_id = "planner_" + secrets.token_urlsafe(24)
            client_name = str(payload.get("client_name", "ChatGPT"))[:120]
            with self.mcp_db() as db:
                db.execute(
                    "INSERT INTO oauth_clients(client_id, client_name, redirect_uris, created_at) VALUES(?,?,?,?)",
                    (client_id, client_name, json.dumps(redirects), clock.time()),
                )
            self.mcp_json(201, {
                "client_id": client_id,
                "client_name": client_name,
                "redirect_uris": redirects,
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            })
        except (ValueError, TypeError, json.JSONDecodeError, sqlite3.Error):
            self.mcp_json(400, {"error": "invalid_client_metadata", "error_description": "Neteisingi OAuth kliento duomenys."})
        return True

    def mcp_authorize(self):
        raw = self.mcp_read_body()
        try:
            form = parse_qs((raw or b"").decode("utf-8"), keep_blank_values=True)
            values = {key: form.get(key, [""])[0] for key in (
                "client_id", "redirect_uri", "response_type", "state", "code_challenge", "code_challenge_method", "resource", "scope", "password", "approve"
            )}
            oauth_fields = {key: values[key] for key in (
                "client_id", "redirect_uri", "response_type", "state", "code_challenge", "code_challenge_method", "resource", "scope"
            )}
            if not self.mcp_valid_authorization_request(oauth_fields):
                raise ValueError("Neteisinga autorizacijos užklausa. Grįžkite į ChatGPT ir bandykite prijungti iš naujo.")
            if values["approve"] != "yes":
                raise ValueError("Prieiga nepatvirtinta.")
            client = self.client_address[0]
            now = clock.time()
            recent = [stamp for stamp in MCP_LOGIN_ATTEMPTS.get(client, []) if now - stamp < 300]
            if len(recent) >= 10:
                MCP_LOGIN_ATTEMPTS[client] = recent
                raise ValueError("Per daug bandymų. Bandykite vėliau.")
            if not self.PLANNER_PASSWORD or not hmac.compare_digest(values["password"], self.PLANNER_PASSWORD):
                recent.append(now)
                MCP_LOGIN_ATTEMPTS[client] = recent
                raise ValueError("Neteisingas planuoklio slaptažodis.")
            MCP_LOGIN_ATTEMPTS.pop(client, None)
            scopes = sorted(set(values["scope"].split()) & {READ_SCOPE, WRITE_SCOPE})
            if not scopes:
                scopes = [READ_SCOPE, WRITE_SCOPE]
            code = secrets.token_urlsafe(32)
            expires = clock.time() + 300
            with self.mcp_db() as db:
                db.execute(
                    "INSERT INTO oauth_codes(code_hash, client_id, redirect_uri, code_challenge, resource, scopes, expires_at) VALUES(?,?,?,?,?,?,?)",
                    (sha256(code.encode()).hexdigest(), values["client_id"], values["redirect_uri"], values["code_challenge"], values["resource"], " ".join(scopes), expires),
                )
            parts = urlparse(values["redirect_uri"])
            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            query.update({"code": code, "state": values["state"]})
            redirect = urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, urlencode(query), parts.fragment))
            self.send_response(302)
            self.send_header("Location", redirect)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (ValueError, sqlite3.Error) as error:
            self.mcp_html(400, "<!doctype html><meta charset=utf-8><title>Prijungti planuoklį</title><h1>Prisijungti nepavyko</h1><p>" + escape(str(error)) + "</p><p>Grįžkite į ChatGPT ir bandykite dar kartą.</p>")
        return True

    def mcp_token(self):
        raw = self.mcp_read_body()
        try:
            form = parse_qs((raw or b"").decode("utf-8"), keep_blank_values=True)
            client_id = form.get("client_id", [""])[0]
            code = form.get("code", [""])[0]
            redirect_uri = form.get("redirect_uri", [""])[0]
            verifier = form.get("code_verifier", [""])[0]
            resource = form.get("resource", [""])[0]
            if form.get("grant_type", [""])[0] != "authorization_code" or not all((client_id, code, redirect_uri, verifier, resource)):
                raise ValueError("invalid_request")
            challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode("ascii")
            code_hash = sha256(code.encode()).hexdigest()
            with self.mcp_db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT client_id, redirect_uri, code_challenge, resource, scopes, expires_at FROM oauth_codes WHERE code_hash=?",
                    (code_hash,),
                ).fetchone()
                if not row or row[5] < clock.time():
                    raise ValueError("invalid_grant")
                if row[0] != client_id or row[1] != redirect_uri or row[2] != challenge or row[3] != resource:
                    raise ValueError("invalid_grant")
                db.execute("DELETE FROM oauth_codes WHERE code_hash=?", (code_hash,))
                token = secrets.token_urlsafe(48)
                expires = clock.time() + TOKEN_TTL
                db.execute(
                    "INSERT INTO oauth_tokens(token_hash, client_id, resource, scopes, expires_at) VALUES(?,?,?,?,?)",
                    (sha256(token.encode()).hexdigest(), client_id, resource, row[4], expires),
                )
            self.mcp_json(200, {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": TOKEN_TTL,
                "scope": row[4],
            })
        except (ValueError, sqlite3.Error) as error:
            code = str(error) or "invalid_grant"
            self.mcp_json(400, {"error": code})
        return True

    def mcp_access(self, required_scope=None):
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not token:
            return None
        try:
            with self.mcp_db() as db:
                row = db.execute(
                    "SELECT resource, scopes, expires_at FROM oauth_tokens WHERE token_hash=?",
                    (sha256(token.encode()).hexdigest(),),
                ).fetchone()
            if not row or row[2] < clock.time() or row[0] != self.mcp_origin() + "/mcp":
                return None
            scopes = set(row[1].split())
            if required_scope and required_scope not in scopes:
                return {"missing_scope": required_scope}
            return {"scopes": scopes}
        except sqlite3.Error:
            return None

    def mcp_auth_error(self, request_id, message, required_scope=None):
        origin = self.mcp_origin()
        scope = required_scope or READ_SCOPE
        challenge = f'Bearer resource_metadata="{origin}/.well-known/oauth-protected-resource", error="insufficient_scope", error_description="{message}", scope="{scope}"'
        self.mcp_json(200, {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": message}],
                "_meta": {"mcp/www_authenticate": [challenge]},
                "isError": True,
            },
        })

    def mcp_tool_definitions(self):
        read_auth = [{"type": "oauth2", "scopes": [READ_SCOPE]}]
        write_auth = [{"type": "oauth2", "scopes": [WRITE_SCOPE]}]
        return [
            {
                "name": "get_day_summary", "title": "Peržiūrėti dienos planą",
                "description": "Use this to read tasks, weight, steps, and health readings for a date. Ask which date if unclear.",
                "inputSchema": {"type": "object", "properties": {"date": {"type": "string", "format": "date", "description": "Data YYYY-MM-DD"}}, "required": ["date"], "additionalProperties": False},
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                "securitySchemes": read_auth,
            },
            {
                "name": "add_task", "title": "Pridėti planuoklio užduotį",
                "description": "Add a task to the daily planner. Use for tasks and reminders, not for weight, steps, pulse, or blood pressure. If date or task text is unclear, ask first. Read the saved result back to the user.",
                "inputSchema": {"type": "object", "properties": {
                    "date": {"type": "string", "format": "date", "description": "Data YYYY-MM-DD"},
                    "text": {"type": "string", "minLength": 1, "maxLength": 120},
                    "category": {"type": "string", "enum": sorted(CATEGORIES)},
                    "time": {"type": "string", "description": "Optional time HH:MM"},
                }, "required": ["date", "text"], "additionalProperties": False},
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
                "securitySchemes": write_auth,
            },
            {
                "name": "record_weight", "title": "Įrašyti svorį",
                "description": "Record the user's weight in kilograms for a date. Ask for the missing date or value; update the existing daily entry when present.",
                "inputSchema": {"type": "object", "properties": {
                    "date": {"type": "string", "format": "date"}, "weight": {"type": "number", "minimum": 1, "maximum": 500},
                }, "required": ["date", "weight"], "additionalProperties": False},
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
                "securitySchemes": write_auth,
            },
            {
                "name": "record_steps", "title": "Įrašyti žingsnių skaičių",
                "description": "Record the number of steps for a date. Ask for the missing date or count; update the existing daily entry when present.",
                "inputSchema": {"type": "object", "properties": {
                    "date": {"type": "string", "format": "date"}, "count": {"type": "integer", "minimum": 0, "maximum": 200000},
                }, "required": ["date", "count"], "additionalProperties": False},
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
                "securitySchemes": write_auth,
            },
            {
                "name": "record_health_reading", "title": "Įrašyti pulsą ir kraujospūdį",
                "description": "Record pulse in beats per minute and systolic/diastolic blood pressure in mmHg. Ask for any missing value or date; update that date's reading. Do not infer medical values.",
                "inputSchema": {"type": "object", "properties": {
                    "date": {"type": "string", "format": "date"}, "pulse": {"type": "integer", "minimum": 20, "maximum": 250},
                    "systolic": {"type": "integer", "minimum": 40, "maximum": 300}, "diastolic": {"type": "integer", "minimum": 20, "maximum": 200},
                }, "required": ["date", "pulse", "systolic", "diastolic"], "additionalProperties": False},
                "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
                "securitySchemes": write_auth,
            },
        ]

    def mcp_instructions(self):
        return (
            "Esu asmeninio planuoklio jungtis. Prieš įrašydamas duomenis patikrink, kad aiškūs jų tipas ir data. "
            "Užduotis dėk į dienos užduotis; kūno svorį, žingsnius ir pulsą/kraujospūdį rašyk tik į atitinkamus laukus. "
            "Jei trūksta datos ar vertės, paklausk. Po įrašymo patvirtink, kas išsaugota. Nediagnozuok pagal sveikatos rodmenis."
        )

    def mcp_rpc(self):
        raw = self.mcp_read_body()
        try:
            message = json.loads(raw or b"")
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            self.mcp_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON-RPC request"}})
            return True

        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized" or (method and method.startswith("notifications/")):
            self.mcp_json(202, {})
            return True
        if method == "initialize":
            requested = message.get("params", {}).get("protocolVersion", "2025-03-26")
            if requested not in SUPPORTED_PROTOCOLS:
                self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Unsupported protocol version"}})
                return True
            self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "daily-planner", "title": "Mano dienos planuoklis", "version": "1.0.0"},
                "instructions": self.mcp_instructions(),
            }})
            return True
        if method == "ping":
            self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "result": {}})
            return True
        if method == "tools/list":
            self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.mcp_tool_definitions(), "nextCursor": None}})
            return True
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            definition = next((tool for tool in self.mcp_tool_definitions() if tool["name"] == name), None)
            if not definition:
                self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": "Nežinomas planuoklio veiksmas."}], "isError": True}})
                return True
            scope = WRITE_SCOPE if not definition["annotations"].get("readOnlyHint") else READ_SCOPE
            access = self.mcp_access(scope)
            if not access or "missing_scope" in access:
                reason = "Prisijunk prie planuoklio, kad galėtum naudoti šį veiksmą."
                self.mcp_auth_error(request_id, reason, scope)
                return True
            try:
                result = self.mcp_call_tool(name, params.get("arguments") or {})
                self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "structuredContent": result,
                    "isError": False,
                }})
            except (ValueError, TypeError) as error:
                self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "result": {
                    "content": [{"type": "text", "text": str(error)}], "isError": True,
                }})
            return True
        if request_id is None:
            self.mcp_json(202, {})
        else:
            self.mcp_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
        return True

    def mcp_call_tool(self, name, args):
        if not isinstance(args, dict):
            raise ValueError("Neteisingi įrankio duomenys.")
        entry_date = str(args.get("date", ""))
        try:
            date.fromisoformat(entry_date)
        except ValueError:
            raise ValueError("Nurodyk datą formatu YYYY-MM-DD.")

        with self.mcp_db() as db:
            if name in ("get_day_summary", "list_tasks"):
                tasks = db.execute(
                    "SELECT id, text, category, time, done FROM tasks WHERE date=? ORDER BY CASE WHEN time='' THEN 1 ELSE 0 END, time, id",
                    (entry_date,),
                ).fetchall()
                weight = db.execute("SELECT weight FROM weights WHERE date=?", (entry_date,)).fetchone()
                steps = db.execute("SELECT count FROM steps WHERE date=?", (entry_date,)).fetchone()
                vitals = db.execute("SELECT pulse,systolic,diastolic FROM vitals WHERE date=?", (entry_date,)).fetchone()
                summary = {"date": entry_date, "tasks": [
                    {"id": row[0], "text": row[1], "category": row[2], "time": row[3], "done": bool(row[4])}
                    for row in tasks
                ]}
                if name == "list_tasks":
                    return {"date": entry_date, "tasks": summary["tasks"]}
                summary["weight_kg"] = weight[0] if weight else None
                summary["steps"] = steps[0] if steps else None
                summary["health"] = ({"pulse_bpm": vitals[0], "systolic_mmhg": vitals[1], "diastolic_mmhg": vitals[2]} if vitals else None)
                return summary

            if name == "add_task":
                text = str(args.get("text", "")).strip()
                category = str(args.get("category", "Kita"))
                task_time = str(args.get("time", ""))
                if not text or len(text) > 120 or category not in CATEGORIES:
                    raise ValueError("Patikrink užduoties tekstą ir kategoriją.")
                try:
                    if task_time:
                        time.fromisoformat(task_time)
                except ValueError:
                    raise ValueError("Laiką nurodyk formatu HH:MM.")
                cursor = db.execute(
                    "INSERT INTO tasks(date,text,category,time) VALUES(?,?,?,?)",
                    (entry_date, text, category, task_time),
                )
                return {"saved": True, "type": "task", "id": cursor.lastrowid, "date": entry_date, "text": text, "category": category, "time": task_time}

            if name == "record_weight":
                raw = args.get("weight")
                if isinstance(raw, bool) or not isinstance(raw, (float, int)) or not math.isfinite(raw) or not 1 <= raw <= 500:
                    raise ValueError("Svoris turi būti nuo 1 iki 500 kg.")
                db.execute(
                    "INSERT INTO weights(date,weight) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET weight=excluded.weight, created_at=CURRENT_TIMESTAMP",
                    (entry_date, float(raw)),
                )
                return {"saved": True, "type": "weight", "date": entry_date, "weight_kg": float(raw)}

            if name == "record_steps":
                count = args.get("count")
                if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 200_000:
                    raise ValueError("Žingsnių skaičius turi būti sveikasis skaičius nuo 0 iki 200 000.")
                db.execute(
                    "INSERT INTO steps(date,count) VALUES(?,?) ON CONFLICT(date) DO UPDATE SET count=excluded.count, created_at=CURRENT_TIMESTAMP",
                    (entry_date, count),
                )
                return {"saved": True, "type": "steps", "date": entry_date, "count": count}

            if name == "record_health_reading":
                pulse, systolic, diastolic = args.get("pulse"), args.get("systolic"), args.get("diastolic")
                values = (pulse, systolic, diastolic)
                if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
                    raise ValueError("Pulsas ir abu spaudimo rodmenys turi būti sveikieji skaičiai.")
                if not 20 <= pulse <= 250 or not 40 <= systolic <= 300 or not 20 <= diastolic <= 200 or systolic <= diastolic:
                    raise ValueError("Patikrink pulso ir kraujospūdžio reikšmes.")
                db.execute(
                    "INSERT INTO vitals(date,pulse,systolic,diastolic) VALUES(?,?,?,?) "
                    "ON CONFLICT(date) DO UPDATE SET pulse=excluded.pulse,systolic=excluded.systolic,diastolic=excluded.diastolic,created_at=CURRENT_TIMESTAMP",
                    (entry_date, pulse, systolic, diastolic),
                )
                return {"saved": True, "type": "health", "date": entry_date, "pulse_bpm": pulse, "systolic_mmhg": systolic, "diastolic_mmhg": diastolic}

        raise ValueError("Nežinomas planuoklio veiksmas.")
