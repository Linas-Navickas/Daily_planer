"""Daily planner web app with shared SQLite storage and a ChatGPT Actions API."""

from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import date, time
import hmac
import json
import os
import secrets
import sqlite3
from time import monotonic


ROOT = Path(__file__).resolve().parent
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "planner.sqlite3"
PLANNER_PASSWORD = os.environ.get("PLANNER_PASSWORD", "")
CHATGPT_API_KEY = os.environ.get("CHATGPT_API_KEY", "")
SESSIONS = set()
LOGIN_ATTEMPTS = {}
CATEGORIES = {"Darbas", "Asmeniniai", "Sveikata", "Kita"}


def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            text TEXT NOT NULL,
            category TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT '',
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS tasks_by_date ON tasks(date, id)")


def task_dict(row):
    return {"id": row[0], "date": row[1], "text": row[2], "category": row[3],
            "time": row[4], "done": bool(row[5])}


class PlannerHandler(SimpleHTTPRequestHandler):
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
        if parsed.path in ("/", "/index.html"):
            self.path = "/index.html"
            return super().do_GET()
        if parsed.path == "/api/session":
            return self.send_json(200, {"authenticated": self.session_id() in SESSIONS})
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
                    "SELECT id, date, text, category, time, done FROM tasks WHERE date=? ORDER BY CASE WHEN time='' THEN 1 ELSE 0 END, time, id",
                    (day,),
                ).fetchall()
            return self.send_json(200, {"tasks": [task_dict(row) for row in rows]})
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            payload = self.read_json()
            password = payload.get("password", "") if isinstance(payload, dict) else ""
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
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
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
            payload = self.read_json()
            if not isinstance(payload, dict):
                return self.send_json(400, {"error": "Netinkami duomenys."})
            task_date = str(payload.get("date", ""))
            text = str(payload.get("text", "")).strip()
            category = str(payload.get("category", "Kita"))
            task_time = str(payload.get("time", ""))
            try:
                date.fromisoformat(task_date)
                if task_time:
                    time.fromisoformat(task_time)
            except ValueError:
                return self.send_json(400, {"error": "Neteisinga data arba laikas."})
            if not text or len(text) > 120 or category not in CATEGORIES:
                return self.send_json(400, {"error": "Patikrinkite užduoties pavadinimą ir kategoriją."})
            with sqlite3.connect(DB_PATH) as db:
                cursor = db.execute(
                    "INSERT INTO tasks(date,text,category,time) VALUES(?,?,?,?)",
                    (task_date, text, category, task_time),
                )
                row = db.execute(
                    "SELECT id, date, text, category, time, done FROM tasks WHERE id=?",
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
        payload = self.read_json()
        if not isinstance(payload, dict) or not isinstance(payload.get("done"), bool):
            return self.send_json(400, {"error": "Reikia nurodyti done true arba false."})
        with sqlite3.connect(DB_PATH) as db:
            result = db.execute("UPDATE tasks SET done=? WHERE id=?", (int(payload["done"]), task_id))
            if not result.rowcount:
                return self.send_json(404, {"error": "Užduotis nerasta."})
            row = db.execute(
                "SELECT id, date, text, category, time, done FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        return self.send_json(200, {"task": task_dict(row)})

    def do_DELETE(self):
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
