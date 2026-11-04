"""Create the planner's initial SQLite schema."""

from alembic import op


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # IF NOT EXISTS preserves databases created by the previous startup initializer.
    op.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        text TEXT NOT NULL,
        category TEXT NOT NULL,
        time TEXT NOT NULL DEFAULT '',
        done INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS tasks_by_date ON tasks(date, id)")
    op.execute("""CREATE TABLE IF NOT EXISTS weights (
        date TEXT PRIMARY KEY,
        weight REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS steps (
        date TEXT PRIMARY KEY,
        count INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS vitals (
        date TEXT PRIMARY KEY,
        pulse INTEGER NOT NULL,
        systolic INTEGER NOT NULL,
        diastolic INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS oauth_clients (
        client_id TEXT PRIMARY KEY,
        client_name TEXT NOT NULL,
        redirect_uris TEXT NOT NULL,
        created_at REAL NOT NULL
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS oauth_codes (
        code_hash TEXT PRIMARY KEY,
        client_id TEXT NOT NULL,
        redirect_uri TEXT NOT NULL,
        code_challenge TEXT NOT NULL,
        resource TEXT NOT NULL,
        scopes TEXT NOT NULL,
        expires_at REAL NOT NULL
    )""")
    op.execute("""CREATE TABLE IF NOT EXISTS oauth_tokens (
        token_hash TEXT PRIMARY KEY,
        client_id TEXT NOT NULL,
        resource TEXT NOT NULL,
        scopes TEXT NOT NULL,
        expires_at REAL NOT NULL
    )""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS oauth_tokens")
    op.execute("DROP TABLE IF EXISTS oauth_codes")
    op.execute("DROP TABLE IF EXISTS oauth_clients")
    op.execute("DROP TABLE IF EXISTS vitals")
    op.execute("DROP TABLE IF EXISTS steps")
    op.execute("DROP TABLE IF EXISTS weights")
    op.execute("DROP INDEX IF EXISTS tasks_by_date")
    op.execute("DROP TABLE IF EXISTS tasks")
