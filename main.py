"""Daily planner HTTP application, served by FastAPI and Uvicorn."""

from contextlib import asynccontextmanager
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import monotonic
from urllib.parse import urlparse
import hmac
import json
import os
import secrets

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import ValidationError
import uvicorn

from mcp_server import PlannerMCPMixin
from database import connect as db_connection, sqlalchemy_url_string
from schemas import LoginRequest, StepsRequest, TaskCreateRequest, TaskDoneRequest, VitalsRequest, WeightRequest


ROOT = Path(__file__).resolve().parent
MCP_TUNNEL_MODE = os.environ.get("MCP_TUNNEL_MODE", "") == "1"
HOST = os.environ.get("HOST", "127.0.0.1" if MCP_TUNNEL_MODE else "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
PLANNER_PASSWORD = os.environ.get("PLANNER_PASSWORD", "")
CHATGPT_API_KEY = os.environ.get("CHATGPT_API_KEY", "")
DEV_AUTO_RELOAD = os.environ.get("DEV_AUTO_RELOAD", "") == "1"
SESSIONS = set()
LOGIN_ATTEMPTS = {}


def app_source_version():
    source_files = [ROOT / "main.py", ROOT / "mcp_server.py", ROOT / "database.py", ROOT / "schemas.py", ROOT / "index.html", ROOT / "app.js"]
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
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_url_string().replace("%", "%%"))
    command.upgrade(config, "head")


def task_dict(row):
    return {"id": row[0], "date": row[1], "text": row[2], "category": row[3],
            "time": row[4], "location": row[5], "done": bool(row[6])}


def session_id(request: Request):
    return request.cookies.get("planner_session", "")


def is_authorized(request: Request):
    auth = request.headers.get("Authorization", "")
    if CHATGPT_API_KEY and auth.startswith("Bearer ") and hmac.compare_digest(auth[7:], CHATGPT_API_KEY):
        return True
    return session_id(request) in SESSIONS


def require_auth(request: Request):
    if not is_authorized(request):
        raise HTTPException(status_code=401, detail="Prisijunkite prie planuoklio.")


def error_response(status: int, message: str):
    return Response(
        content=json.dumps({"error": message}, ensure_ascii=False), status_code=status,
        media_type="application/json", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


class MCPRequestAdapter(PlannerMCPMixin):
    """Small bridge that lets existing MCP/OAuth handlers return ASGI responses."""

    PLANNER_PASSWORD = PLANNER_PASSWORD
    MCP_TUNNEL_MODE = MCP_TUNNEL_MODE

    def __init__(self, request: Request, body: bytes):
        self.request = request
        self.headers = request.headers
        self.rfile = BytesIO(body)
        self.client_address = (request.client.host if request.client else "", request.client.port if request.client else 0)
        self.path = request.url.path
        self._status = 200
        self._headers = {}
        self._body = b""

    def send_response(self, status, message=None):
        self._status = status

    def send_header(self, name, value):
        self._headers[name] = value

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self

    def write(self, body):
        self._body += body

    def as_response(self):
        media_type = self._headers.pop("Content-Type", None)
        if media_type and media_type.startswith("application/json"):
            media_type = None  # The encoded payload and explicit header already include UTF-8.
        response = Response(content=self._body, status_code=self._status, media_type=media_type, headers=self._headers)
        if media_type is None and "Content-Type" not in response.headers:
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.environ.get("RUN_MIGRATIONS", "1") == "1":
        initialize_database()
    else:
        with db_connection() as db:
            db.execute("SELECT 1")
    yield


app = FastAPI(title="Daily Planner", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/healthz", include_in_schema=False)
async def healthcheck():
    with db_connection() as db:
        db.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
async def index():
    return FileResponse(ROOT / "index.html", media_type="text/html; charset=utf-8")


@app.get("/app.js", include_in_schema=False)
async def javascript():
    return FileResponse(ROOT / "app.js", media_type="text/javascript; charset=utf-8")


@app.get("/api/dev-version")
async def dev_version(request: Request):
    # Docker's loopback-only host port may appear as a bridge IP inside this container.
    is_local = not request.headers.get("CF-Connecting-IP")
    if not DEV_AUTO_RELOAD or not is_local:
        return error_response(404, "Nerasta.")
    return {"version": app_source_version()}


@app.get("/api/session")
async def get_session(request: Request):
    return {"authenticated": session_id(request) in SESSIONS}


@app.get("/api/weights")
async def get_weights(request: Request):
    require_auth(request)
    with db_connection() as db:
        rows = db.execute("SELECT date, weight FROM weights ORDER BY date DESC LIMIT 365").fetchall()
    return {"weights": [{"date": row[0], "weight": row[1]} for row in rows]}


@app.get("/api/steps")
async def get_steps(request: Request):
    require_auth(request)
    with db_connection() as db:
        rows = db.execute("SELECT date, count FROM steps ORDER BY date DESC LIMIT 365").fetchall()
    return {"steps": [{"date": row[0], "count": row[1]} for row in rows]}


@app.get("/api/vitals")
async def get_vitals(request: Request):
    require_auth(request)
    with db_connection() as db:
        rows = db.execute("SELECT date, pulse, systolic, diastolic FROM vitals ORDER BY date DESC LIMIT 365").fetchall()
    return {"vitals": [{"date": row[0], "pulse": row[1], "systolic": row[2], "diastolic": row[3]} for row in rows]}


@app.get("/api/tasks")
async def get_tasks(request: Request, day: str = ""):
    require_auth(request)
    day = request.query_params.get("date", "")
    try:
        date.fromisoformat(day)
    except ValueError:
        return error_response(400, "Data turi būti YYYY-MM-DD formatu.")
    with db_connection() as db:
        rows = db.execute(
            "SELECT id, date, text, category, time, location, done FROM tasks WHERE date=? ORDER BY CASE WHEN time='' THEN 1 ELSE 0 END, time, id",
            (day,),
        ).fetchall()
    return {"tasks": [task_dict(row) for row in rows]}


@app.get("/api/tasks/all")
async def get_all_tasks(request: Request):
    require_auth(request)
    with db_connection() as db:
        rows = db.execute(
            "SELECT id, date, text, category, time, location, done FROM tasks "
            "ORDER BY date DESC, CASE WHEN time='' THEN 1 ELSE 0 END, time, id DESC"
        ).fetchall()
    return {"tasks": [task_dict(row) for row in rows]}


async def validated_body(request: Request, model, message: str):
    raw = await request.body()
    if not raw or len(raw) > 16_384:
        return None, error_response(400, message)
    try:
        return model.model_validate_json(raw), None
    except ValidationError:
        return None, error_response(400, message)


@app.post("/api/weights")
async def record_weight(request: Request):
    require_auth(request)
    value, error = await validated_body(request, WeightRequest, "Nurodykite tinkamą datą ir svorį (1–500 kg).")
    if error:
        return error
    entry_date = value.date.isoformat()
    with db_connection() as db:
        db.execute("INSERT INTO weights(date, weight) VALUES(?, ?) ON CONFLICT(date) DO UPDATE SET weight=excluded.weight, created_at=CURRENT_TIMESTAMP", (entry_date, value.weight))
    return {"weight": {"date": entry_date, "weight": value.weight}}


@app.post("/api/steps")
async def record_steps(request: Request):
    require_auth(request)
    value, error = await validated_body(request, StepsRequest, "Nurodykite tinkamą datą ir žingsnių skaičių (0–200 000).")
    if error:
        return error
    entry_date = value.date.isoformat()
    with db_connection() as db:
        db.execute("INSERT INTO steps(date, count) VALUES(?, ?) ON CONFLICT(date) DO UPDATE SET count=excluded.count, created_at=CURRENT_TIMESTAMP", (entry_date, value.count))
    return {"steps": {"date": entry_date, "count": value.count}}


@app.post("/api/vitals")
async def record_vitals(request: Request):
    require_auth(request)
    value, error = await validated_body(request, VitalsRequest, "Patikrinkite datą, pulsą ir kraujospūdžio rodmenis.")
    if error:
        return error
    entry_date = value.date.isoformat()
    with db_connection() as db:
        db.execute("INSERT INTO vitals(date, pulse, systolic, diastolic) VALUES(?, ?, ?, ?) ON CONFLICT(date) DO UPDATE SET pulse=excluded.pulse, systolic=excluded.systolic, diastolic=excluded.diastolic, created_at=CURRENT_TIMESTAMP", (entry_date, value.pulse, value.systolic, value.diastolic))
    return {"vitals": {"date": entry_date, "pulse": value.pulse, "systolic": value.systolic, "diastolic": value.diastolic}}


@app.post("/api/login")
async def login(request: Request, response: Response):
    value, error = await validated_body(request, LoginRequest, "Nurodykite slaptažodį.")
    if error:
        return error
    if not PLANNER_PASSWORD:
        return error_response(503, "Nustatykite PLANNER_PASSWORD serverio aplinkoje.")
    client = request.client.host if request.client else "unknown"
    now = monotonic()
    recent = [stamp for stamp in LOGIN_ATTEMPTS.get(client, []) if now - stamp < 300]
    if len(recent) >= 10:
        LOGIN_ATTEMPTS[client] = recent
        return error_response(429, "Per daug bandymų. Bandykite vėliau.")
    if not hmac.compare_digest(value.password, PLANNER_PASSWORD):
        recent.append(now)
        LOGIN_ATTEMPTS[client] = recent
        return error_response(401, "Neteisingas slaptažodis.")
    LOGIN_ATTEMPTS.pop(client, None)
    session = secrets.token_urlsafe(32)
    SESSIONS.add(session)
    forwarded_proto = request.headers.get("X-Forwarded-Proto", request.headers.get("X_Forwarded_Proto", ""))
    forwarded = request.headers.get("Forwarded", "").lower()
    secure = forwarded_proto.lower() == "https" or "proto=https" in forwarded
    response.set_cookie("planner_session", session, httponly=True, samesite="strict", path="/", max_age=2_592_000, secure=secure)
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": True}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    SESSIONS.discard(session_id(request))
    response.delete_cookie("planner_session", httponly=True, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}


@app.post("/api/tasks", status_code=201)
async def create_task(request: Request):
    require_auth(request)
    value, error = await validated_body(request, TaskCreateRequest, "Patikrinkite užduoties tekstą, datą, kategoriją, laiką ir vietą.")
    if error:
        return error
    with db_connection() as db:
        cursor = db.execute("INSERT INTO tasks(date,text,category,time,location) VALUES(?,?,?,?,?)", (value.date.isoformat(), value.text, value.category, value.time, value.location))
        row = db.execute("SELECT id, date, text, category, time, location, done FROM tasks WHERE id=?", (cursor.lastrowid,)).fetchone()
    return {"task": task_dict(row)}


@app.patch("/api/tasks/{task_id}")
async def set_task_done(task_id: int, request: Request):
    require_auth(request)
    value, error = await validated_body(request, TaskDoneRequest, "Reikia nurodyti done true arba false.")
    if error:
        return error
    with db_connection() as db:
        result = db.execute("UPDATE tasks SET done=? WHERE id=?", (int(value.done), task_id))
        if not result.rowcount:
            return error_response(404, "Užduotis nerasta.")
        row = db.execute("SELECT id, date, text, category, time, location, done FROM tasks WHERE id=?", (task_id,)).fetchone()
    return {"task": task_dict(row)}


@app.delete("/api/tasks/{task_id}")
async def remove_task(task_id: int, request: Request):
    require_auth(request)
    with db_connection() as db:
        result = db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    if not result.rowcount:
        return error_response(404, "Užduotis nerasta.")
    return {"deleted": True}


@app.delete("/api/{record_type}/{entry_date}")
async def remove_daily_record(record_type: str, entry_date: str, request: Request):
    tables = {"weights": ("Svorio įrašas nerastas.",), "steps": ("Žingsnių įrašas nerastas.",), "vitals": ("Sveikatos įrašas nerastas.",)}
    if record_type not in tables:
        return error_response(404, "Nerasta.")
    require_auth(request)
    try:
        date.fromisoformat(entry_date)
    except ValueError:
        return error_response(400, "Neteisinga data.")
    with db_connection() as db:
        result = db.execute(f"DELETE FROM {record_type} WHERE date=?", (entry_date,))
    if not result.rowcount:
        return error_response(404, tables[record_type][0])
    return {"deleted": True}


@app.api_route("/.well-known/{metadata_path:path}", methods=["GET"])
@app.api_route("/authorize", methods=["GET", "POST"])
@app.api_route("/register", methods=["POST"])
@app.api_route("/token", methods=["POST"])
@app.api_route("/mcp", methods=["GET", "POST"])
async def mcp_routes(request: Request):
    adapter = MCPRequestAdapter(request, await request.body())
    parsed = urlparse(str(request.url))
    handled = adapter.handle_mcp_get(parsed) if request.method == "GET" else adapter.handle_mcp_post(parsed)
    if handled:
        return adapter.as_response()
    return error_response(404, "Nerasta.")


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info", proxy_headers=True, forwarded_allow_ips="*")
