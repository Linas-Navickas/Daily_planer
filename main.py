"""Daily planner web app with shared SQLite storage and a ChatGPT Actions API."""

from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import date
from hashlib import sha256
import hmac
import json
import os
import secrets
import sqlite3
from time import monotonic
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from mcp_server import PlannerMCPMixin
from schemas import LoginRequest, StepsRequest, TaskCreateRequest, TaskDoneRequest, VitalsRequest, WeightRequest


ROOT = Path(__file__).resolve().parent
MCP_TUNNEL_MODE = os.environ.get("MCP_TUNNEL_MODE", "") == "1"
HOST = "127.0.0.1" if MCP_TUNNEL_MODE else os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "planner.sqlite3"
PLANNER_PASSWORD = os.environ.get("PLANNER_PASSWORD", "")
CHATGPT_API_KEY = os.environ.get("CHATGPT_API_KEY", "")
DEV_AUTO_RELOAD = os.environ.get("DEV_AUTO_RELOAD", "") == "1"
SESSIONS = set()
LOGIN_ATTEMPTS = {}


def app_source_version():
    source_files = [ROOT / "main.py", ROOT / "schemas.py", ROOT / "index.html", ROOT / "app.js"]
    migration_dir = ROOT / "migrations" / "versions"
    if migration_dir.exists():
        source_files.extend(sorted(migration_dir.glob("*.py")))
    digest = sha256()
    for source in source_files:
        if source.is_file():
            digest.update(source.relative_to(ROOT).as_posix().encode("utf-8"))
            digest.update(source.read_bytes())
    return digest.hexdigest()


def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / "alembic.ini"))
    database_url = "sqlite:///" + DB_PATH.as_posix().replace("%", "%%")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def task_dict(row):
    return {"id": row[0], "date": row[1], "text": row[2], "category": row[3],
            "time": row[4], "location": row[5], "done": bool(row[6])}


class PlannerHandler(PlannerMCPMixin, SimpleHTTPRequestHandler):
    DB_PATH = DB_PATH
    PLANNER_PASSWORD = PLANNER_PASSWORD
    MCP_TUNNEL_MODE = MCP_TUNNEL_MODE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        # Avoid logging task text or authorization headers.
        super().log_message(format, *args)

    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 16_384:
                return None
            return json.loads(self.rfile.read(size))
        except (ValueError, json.JSONDecodeError):
            return None

    def validate_json(self, model, error_message):
        try:
            return model.model_validate(self.read_json())
        except ValidationError:
            self.send_json(400, {"error": error_message})
            return None

    def session_id(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            morsel = cookie.get("planner_session")
            return morsel.value if morsel else ""
        except Exception:
            return ""

    def authorized(self):
        auth = self.headers.get("Authorization", "")
        if CHATGPT_API_KEY and auth.startswith("Bearer "):
            if hmac.compare_digest(auth[7:], CHATGPT_API_KEY):
                return True
        return self.session_id() in SESSIONS

    def require_auth(self):
        if not self.authorized():
            self.send_json(401, {"error": "Prisijunkite prie planuoklio."})
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)
        if self.handle_mcp_get(parsed):
            return
        if parsed.path == "/api/dev-version":
            is_local = self.client_address[0] in ("127.0.0.1", "::1")
            is_tunneled = bool(self.headers.get("CF-Connecting-IP"))
            if not DEV_AUTO_RELOAD or not is_local or is_tunneled:
                return self.send_json(404, {"error": "Nerasta."})
            return self.send_json(200, {"version": app_source_version()})
        if parsed.path in ("/", "/index.html", "/app.js"):
            self.path = "/index.html" if parsed.path == "/" else parsed.path
            return super().do_GET()
        if parsed.path == "/api/session":
            return self.send_json(200, {"authenticated": self.session_id() in SESSIONS})
        if parsed.path == "/api/weights":
            if not self.require_auth():
                return
            with sqlite3.connect(DB_PATH) as db:
                rows = db.execute(
                    "SELECT date, weight FROM weights ORDER BY date DESC LIMIT 365"
                ).fetchall()
            return self.send_json(200, {"weights": [{"date": row[0], "weight": row[1]} for row in rows]})
        if parsed.path == "/api/steps":
            if not self.require_auth():
                return
            with sqlite3.connect(DB_PATH) as db:
                rows = db.execute(
                    "SELECT date, count FROM steps ORDER BY date DESC LIMIT 365"
                ).fetchall()
            return self.send_json(200, {"steps": [{"date": row[0], "count": row[1]} for row in rows]})
        if parsed.path == "/api/vitals":
            if not self.require_auth():
                return
            with sqlite3.connect(DB_PATH) as db:
                rows = db.execute(
                    "SELECT date, pulse, systolic, diastolic FROM vitals ORDER BY date DESC LIMIT 365"
                ).fetchall()
            return self.send_json(200, {"vitals": [
                {"date": row[0], "pulse": row[1], "systolic": row[2], "diastolic": row[3]}
                for row in rows
            ]})
        if parsed.path == "/api/tasks":
            if not self.require_auth():
                return
            query = parse_qs(parsed.query)
            day = query.get("date", [""])[0]
            try:
                date.fromisoformat(day)
            except ValueError:
                return self.send_json(400, {"error": "Data turi būti YYYY-MM-DD formatu."})
            with sqlite3.connect(DB_PATH) as db:
                rows = db.execute(
                    "SELECT id, date, text, category, time, location, done FROM tasks WHERE date=? ORDER BY CASE WHEN time='' THEN 1 ELSE 0 END, time, id",
                    (day,),
                ).fetchall()
            return self.send_json(200, {"tasks": [task_dict(row) for row in rows]})
        return self.send_json(404, {"error": "Nerasta."})

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html", "/app.js"):
            self.path = "/index.html" if parsed.path == "/" else parsed.path
            return super().do_HEAD()
        return self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if self.handle_mcp_post(parsed):
            return
        if parsed.path == "/api/weights":
            if not self.require_auth():
                return
            request = self.validate_json(WeightRequest, "Nurodykite tinkamą datą ir svorį (1–500 kg).")
            if request is None:
                return
            entry_date = request.date.isoformat()
            weight = request.weight
            with sqlite3.connect(DB_PATH) as db:
                db.execute(
                    "INSERT INTO weights(date, weight) VALUES(?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET weight=excluded.weight, created_at=CURRENT_TIMESTAMP",
                    (entry_date, weight),
                )
            return self.send_json(200, {"weight": {"date": entry_date, "weight": weight}})
        if parsed.path == "/api/steps":
            if not self.require_auth():
                return
            request = self.validate_json(StepsRequest, "Nurodykite tinkamą datą ir žingsnių skaičių (0–200 000).")
            if request is None:
                return
            entry_date = request.date.isoformat()
            steps = request.count
            with sqlite3.connect(DB_PATH) as db:
                db.execute(
                    "INSERT INTO steps(date, count) VALUES(?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET count=excluded.count, created_at=CURRENT_TIMESTAMP",
                    (entry_date, steps),
                )
            return self.send_json(200, {"steps": {"date": entry_date, "count": steps}})
        if parsed.path == "/api/vitals":
            if not self.require_auth():
                return
            request = self.validate_json(VitalsRequest, "Patikrinkite datą, pulsą ir kraujospūdžio rodmenis.")
            if request is None:
                return
            entry_date = request.date.isoformat()
            pulse, systolic, diastolic = request.pulse, request.systolic, request.diastolic
            with sqlite3.connect(DB_PATH) as db:
                db.execute(
                    "INSERT INTO vitals(date, pulse, systolic, diastolic) VALUES(?, ?, ?, ?) "
                    "ON CONFLICT(date) DO UPDATE SET pulse=excluded.pulse, systolic=excluded.systolic, "
                    "diastolic=excluded.diastolic, created_at=CURRENT_TIMESTAMP",
                    (entry_date, pulse, systolic, diastolic),
                )
            return self.send_json(200, {"vitals": {
                "date": entry_date, "pulse": pulse, "systolic": systolic, "diastolic": diastolic
            }})
        if parsed.path == "/api/login":
            request = self.validate_json(LoginRequest, "Nurodykite slaptažodį.")
            if request is None:
                return
            password = request.password
            if not PLANNER_PASSWORD:
                return self.send_json(503, {"error": "Nustatykite PLANNER_PASSWORD serverio aplinkoje."})
            client = self.client_address[0]
            now = monotonic()
            recent = [stamp for stamp in LOGIN_ATTEMPTS.get(client, []) if now - stamp < 300]
            if len(recent) >= 10:
                LOGIN_ATTEMPTS[client] = recent
                return self.send_json(429, {"error": "Per daug bandymų. Bandykite vėliau."})
            if not hmac.compare_digest(str(password), PLANNER_PASSWORD):
                recent.append(now)
                LOGIN_ATTEMPTS[client] = recent
                return self.send_json(401, {"error": "Neteisingas slaptažodis."})
            LOGIN_ATTEMPTS.pop(client, None)
            session = secrets.token_urlsafe(32)
            SESSIONS.add(session)
            forwarded_proto = self.headers.get("X-Forwarded-Proto", self.headers.get("X_Forwarded_Proto", ""))
            forwarded = self.headers.get("Forwarded", "").lower()
            secure = "; Secure" if forwarded_proto.lower() == "https" or "proto=https" in forwarded else ""
            return self.send_json(200, {"authenticated": True}, {
                "Set-Cookie": f"planner_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000{secure}"
            })
        if parsed.path == "/api/logout":
            SESSIONS.discard(self.session_id())
            return self.send_json(200, {"authenticated": False}, {
                "Set-Cookie": "planner_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
            })
        if parsed.path == "/api/tasks":
            if not self.require_auth():
                return
            request = self.validate_json(TaskCreateRequest, "Patikrinkite užduoties tekstą, datą, kategoriją, laiką ir vietą.")
            if request is None:
                return
            task_date = request.date.isoformat()
            text, category, task_time, location = request.text, request.category, request.time, request.location
            with sqlite3.connect(DB_PATH) as db:
                cursor = db.execute(
                    "INSERT INTO tasks(date,text,category,time,location) VALUES(?,?,?,?,?)",
                    (task_date, text, category, task_time, location),
                )
                row = db.execute(
                    "SELECT id, date, text, category, time, location, done FROM tasks WHERE id=?",
                    (cursor.lastrowid,),
                ).fetchone()
            return self.send_json(201, {"task": task_dict(row)})
        return self.send_json(404, {"error": "Nerasta."})

    def do_PATCH(self):
        if not self.path.startswith("/api/tasks/"):
            return self.send_json(404, {"error": "Nerasta."})
        if not self.require_auth():
            return
        try:
            task_id = int(self.path.rsplit("/", 1)[1])
        except ValueError:
            return self.send_json(400, {"error": "Neteisingas užduoties numeris."})
        request = self.validate_json(TaskDoneRequest, "Reikia nurodyti done true arba false.")
        if request is None:
            return
        with sqlite3.connect(DB_PATH) as db:
            result = db.execute("UPDATE tasks SET done=? WHERE id=?", (int(request.done), task_id))
            if not result.rowcount:
                return self.send_json(404, {"error": "Užduotis nerasta."})
            row = db.execute(
                "SELECT id, date, text, category, time, location, done FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        return self.send_json(200, {"task": task_dict(row)})

    def do_DELETE(self):
        if self.path.startswith("/api/vitals/"):
            if not self.require_auth():
                return
            entry_date = self.path.rsplit("/", 1)[1]
            try:
                date.fromisoformat(entry_date)
            except ValueError:
                return self.send_json(400, {"error": "Neteisinga data."})
            with sqlite3.connect(DB_PATH) as db:
                result = db.execute("DELETE FROM vitals WHERE date=?", (entry_date,))
            if not result.rowcount:
                return self.send_json(404, {"error": "Sveikatos įrašas nerastas."})
            return self.send_json(200, {"deleted": True})
        if self.path.startswith("/api/steps/"):
            if not self.require_auth():
                return
            entry_date = self.path.rsplit("/", 1)[1]
            try:
                date.fromisoformat(entry_date)
            except ValueError:
                return self.send_json(400, {"error": "Neteisinga data."})
            with sqlite3.connect(DB_PATH) as db:
                result = db.execute("DELETE FROM steps WHERE date=?", (entry_date,))
            if not result.rowcount:
                return self.send_json(404, {"error": "Žingsnių įrašas nerastas."})
            return self.send_json(200, {"deleted": True})
        if self.path.startswith("/api/weights/"):
            if not self.require_auth():
                return
            entry_date = self.path.rsplit("/", 1)[1]
            try:
                date.fromisoformat(entry_date)
            except ValueError:
                return self.send_json(400, {"error": "Neteisinga data."})
            with sqlite3.connect(DB_PATH) as db:
                result = db.execute("DELETE FROM weights WHERE date=?", (entry_date,))
            if not result.rowcount:
                return self.send_json(404, {"error": "Svorio įrašas nerastas."})
            return self.send_json(200, {"deleted": True})
        if not self.path.startswith("/api/tasks/"):
            return self.send_json(404, {"error": "Nerasta."})
        if not self.require_auth():
            return
        try:
            task_id = int(self.path.rsplit("/", 1)[1])
        except ValueError:
            return self.send_json(400, {"error": "Neteisingas užduoties numeris."})
        with sqlite3.connect(DB_PATH) as db:
            result = db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        if not result.rowcount:
            return self.send_json(404, {"error": "Užduotis nerasta."})
        return self.send_json(200, {"deleted": True})


if __name__ == "__main__":
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), PlannerHandler)
    print(f"Mano planuoklis veikia: http://localhost:{PORT}")
    print("Sustabdykite serverį paspaudę Ctrl+C.")
    if not PLANNER_PASSWORD:
        print("Nustatykite PLANNER_PASSWORD, kad galėtumėte prisijungti.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPlanuoklis sustabdytas.")
    finally:
        server.server_close()
