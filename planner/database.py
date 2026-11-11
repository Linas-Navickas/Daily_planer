"""PostgreSQL connection helpers shared by the HTTP API and MCP handlers."""

import os
import re

import psycopg
from sqlalchemy.engine import URL

DatabaseError = psycopg.Error


def sqlalchemy_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgres://")
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        return url
    return URL.create(
        "postgresql+psycopg",
        username=os.environ.get("PGUSER", "planner"),
        password=os.environ.get("PGPASSWORD", "planner"),
        host=os.environ.get("PGHOST", "127.0.0.1"),
        port=int(os.environ.get("PGPORT", "5432")),
        database=os.environ.get("PGDATABASE", "planner"),
    )


def sqlalchemy_url_string():
    url = sqlalchemy_url()
    if isinstance(url, URL):
        return url.render_as_string(hide_password=False)
    return url


class Cursor:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class Connection:
    """Expose the small execute/fetch interface used by this application."""

    def __init__(self):
        dsn = os.environ.get("DATABASE_URL")
        if dsn:
            dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
            self._connection = psycopg.connect(dsn)
        else:
            self._connection = psycopg.connect()

    def execute(self, statement, parameters=()):
        if statement.strip().upper() == "BEGIN IMMEDIATE":
            statement = "BEGIN"
        statement = statement.replace("?", "%s")
        is_task_insert = bool(re.match(r"\s*INSERT\s+INTO\s+tasks\b", statement, re.IGNORECASE))
        if is_task_insert and "RETURNING" not in statement.upper():
            statement += " RETURNING id"
        cursor = self._connection.cursor()
        cursor.execute(statement, parameters)
        inserted_id = cursor.fetchone()[0] if is_task_insert else None
        return Cursor(cursor, lastrowid=inserted_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self.close()

    def close(self):
        self._connection.close()


def connect():
    return Connection()
