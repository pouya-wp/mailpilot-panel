"""SQLite access layer.

Deliberately raw sqlite3 rather than an ORM. The schema here is fixed and
hand-shaped, every query is a page's worth of columns, and the whole database
is one file — an ORM would add a dependency, a migration story and a lazy-load
footgun without removing a single line of real work.

What this module DOES provide, because hand-written SQL without them is where
the bugs live:

* one connection per request, with foreign keys and WAL actually turned on
  (sqlite disables FK enforcement by default, which quietly lets orphans in);
* `Row` results that behave like dicts, so routers never index by position;
* helpers that take parameters, never f-strings — the only safe way to build
  a query with user input in it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .config import settings

_local = threading.local()


# ---------------------------------------------------------------- connection


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    # FK enforcement is OFF by default in sqlite and has to be asked for on
    # every single connection, not once on the file.
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets readers run while a write is in flight, which matters as soon as
    # the dashboard fires half a dozen parallel requests.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")


def connect() -> sqlite3.Connection:
    """The calling thread's connection, opened on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = settings.db_path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        _configure(conn)
        _local.conn = conn
    return conn


def close() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """All-or-nothing. A half-applied mutation is worse than a failed one."""
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# ---------------------------------------------------------------- queries


def query(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, params).fetchall()


def one(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, params).fetchone()


def scalar(sql: str, params: Sequence[Any] | dict[str, Any] = (), default: Any = None) -> Any:
    row = one(sql, params)
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def execute(sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
    return connect().execute(sql, params)


def executemany(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    connect().executemany(sql, rows)


def insert(table: str, data: dict[str, Any]) -> None:
    """Column names come from OUR code, values are always bound."""
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(data.values()))


def upsert(table: str, data: dict[str, Any], key: str = "id") -> None:
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    updates = ", ".join(f"{c}=excluded.{c}" for c in data if c != key)
    execute(
        f"INSERT INTO {table} ({cols}) VALUES ({marks}) "
        f"ON CONFLICT({key}) DO UPDATE SET {updates}",
        list(data.values()),
    )


def update(table: str, row_id: str, data: dict[str, Any], key: str = "id") -> None:
    if not data:
        return
    sets = ", ".join(f"{c} = ?" for c in data)
    execute(f"UPDATE {table} SET {sets} WHERE {key} = ?", [*data.values(), row_id])


# ---------------------------------------------------------------- json cols

def loads(value: Any, default: Any = None) -> Any:
    if value in (None, ""):
        return default if default is not None else []
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# ---------------------------------------------------------------- schema

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  plan          TEXT NOT NULL DEFAULT 'scale',
  timezone      TEXT NOT NULL DEFAULT 'Asia/Tehran',
  default_lang  TEXT NOT NULL DEFAULT 'en',
  from_name     TEXT NOT NULL DEFAULT 'Acme',
  from_email    TEXT NOT NULL DEFAULT 'hello@mail.acme.io',
  reply_to      TEXT NOT NULL DEFAULT 'replies@mail.acme.io',
  footer        TEXT NOT NULL DEFAULT '',
  throttle_per_hour INTEGER NOT NULL DEFAULT 40000,
  quiet_hours   INTEGER NOT NULL DEFAULT 1,
  quiet_from    TEXT NOT NULL DEFAULT '21:00',
  quiet_to      TEXT NOT NULL DEFAULT '08:00',
  default_model TEXT NOT NULL DEFAULT 'claude-opus-5',
  creativity    INTEGER NOT NULL DEFAULT 60,
  auto_approve  INTEGER NOT NULL DEFAULT 0,
  gdpr          INTEGER NOT NULL DEFAULT 1,
  retention_months INTEGER NOT NULL DEFAULT 24,
  notif         TEXT NOT NULL DEFAULT '{}',
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id            TEXT PRIMARY KEY,
  email         TEXT NOT NULL UNIQUE,
  name_en       TEXT NOT NULL,
  name_fa       TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'viewer',
  password_hash TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'active',
  last_active_at TEXT,
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
  id            TEXT PRIMARY KEY,
  name_en       TEXT NOT NULL, name_fa TEXT NOT NULL,
  role_en       TEXT NOT NULL, role_fa TEXT NOT NULL,
  emoji         TEXT NOT NULL DEFAULT '',
  tint          TEXT NOT NULL DEFAULT '',
  model         TEXT NOT NULL,
  autonomy      TEXT NOT NULL DEFAULT 'approve',
  status        TEXT NOT NULL DEFAULT 'active',
  runs          INTEGER NOT NULL DEFAULT 0,
  success       REAL NOT NULL DEFAULT 0,
  actions_today INTEGER NOT NULL DEFAULT 0,
  budget        INTEGER NOT NULL DEFAULT 100,
  temperature   REAL NOT NULL DEFAULT 0.5,
  last_run_at   TEXT,
  skills        TEXT NOT NULL DEFAULT '[]',
  tools         TEXT NOT NULL DEFAULT '[]',
  instructions  TEXT NOT NULL DEFAULT '',
  memory        TEXT NOT NULL DEFAULT '[]',
  sparkline     TEXT NOT NULL DEFAULT '[]',
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
  id         TEXT PRIMARY KEY,
  name_en    TEXT NOT NULL, name_fa TEXT NOT NULL,
  emoji      TEXT NOT NULL DEFAULT '',
  tint       TEXT NOT NULL DEFAULT '',
  size       INTEGER NOT NULL DEFAULT 0,
  growth     REAL NOT NULL DEFAULT 0,
  open_rate  REAL NOT NULL DEFAULT 0,
  live       INTEGER NOT NULL DEFAULT 1,
  match_mode TEXT NOT NULL DEFAULT 'all',
  rules      TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
  id          TEXT PRIMARY KEY,
  name_en     TEXT NOT NULL, name_fa TEXT NOT NULL,
  subject_en  TEXT NOT NULL DEFAULT '', subject_fa TEXT NOT NULL DEFAULT '',
  body_en     TEXT NOT NULL DEFAULT '', body_fa TEXT NOT NULL DEFAULT '',
  type        TEXT NOT NULL DEFAULT 'broadcast',
  status      TEXT NOT NULL DEFAULT 'draft',
  agent_id    TEXT REFERENCES agents(id) ON DELETE SET NULL,
  segment_id  TEXT REFERENCES segments(id) ON DELETE SET NULL,
  recipients  INTEGER NOT NULL DEFAULT 0,
  sent        INTEGER NOT NULL DEFAULT 0,
  delivered   INTEGER NOT NULL DEFAULT 0,
  opens       INTEGER NOT NULL DEFAULT 0,
  clicks      INTEGER NOT NULL DEFAULT 0,
  replies     INTEGER NOT NULL DEFAULT 0,
  unsubs      INTEGER NOT NULL DEFAULT 0,
  bounces     INTEGER NOT NULL DEFAULT 0,
  revenue     REAL NOT NULL DEFAULT 0,
  scheduled_for TEXT,
  trend       TEXT NOT NULL DEFAULT '[]',
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_updated ON campaigns(updated_at DESC);

CREATE TABLE IF NOT EXISTS contacts (
  id         TEXT PRIMARY KEY,
  name_en    TEXT NOT NULL, name_fa TEXT NOT NULL,
  email      TEXT NOT NULL UNIQUE,
  status     TEXT NOT NULL DEFAULT 'subscribed',
  score      INTEGER NOT NULL DEFAULT 0,
  ltv        REAL NOT NULL DEFAULT 0,
  orders     INTEGER NOT NULL DEFAULT 0,
  tags       TEXT NOT NULL DEFAULT '[]',
  source_id  TEXT NOT NULL DEFAULT 'signup',
  source_en  TEXT NOT NULL DEFAULT '', source_fa TEXT NOT NULL DEFAULT '',
  country    TEXT NOT NULL DEFAULT '',
  device     TEXT NOT NULL DEFAULT 'desktop',
  last_open_at TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_contacts_score ON contacts(score DESC);

CREATE TABLE IF NOT EXISTS templates (
  id       TEXT PRIMARY KEY,
  name_en  TEXT NOT NULL, name_fa TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'promo',
  used     INTEGER NOT NULL DEFAULT 0,
  accent   TEXT NOT NULL DEFAULT '#7ba3cd',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journeys (
  id         TEXT PRIMARY KEY,
  name_en    TEXT NOT NULL, name_fa TEXT NOT NULL,
  trigger_en TEXT NOT NULL, trigger_fa TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'active',
  enrolled   INTEGER NOT NULL DEFAULT 0,
  completed  INTEGER NOT NULL DEFAULT 0,
  conversion REAL NOT NULL DEFAULT 0,
  agent_id   TEXT REFERENCES agents(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journey_steps (
  id         TEXT PRIMARY KEY,
  journey_id TEXT NOT NULL REFERENCES journeys(id) ON DELETE CASCADE,
  position   INTEGER NOT NULL,
  type       TEXT NOT NULL,
  label_en   TEXT NOT NULL, label_fa TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_steps_journey ON journey_steps(journey_id, position);

CREATE TABLE IF NOT EXISTS threads (
  id          TEXT PRIMARY KEY,
  from_en     TEXT NOT NULL, from_fa TEXT NOT NULL,
  email       TEXT NOT NULL,
  subject_en  TEXT NOT NULL, subject_fa TEXT NOT NULL,
  preview_en  TEXT NOT NULL, preview_fa TEXT NOT NULL,
  draft_en    TEXT NOT NULL DEFAULT '', draft_fa TEXT NOT NULL DEFAULT '',
  intent      TEXT NOT NULL DEFAULT 'question',
  sentiment   REAL NOT NULL DEFAULT 0.5,
  handled     INTEGER NOT NULL DEFAULT 0,
  agent_id    TEXT REFERENCES agents(id) ON DELETE SET NULL,
  assignee_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  snoozed_until TEXT,
  received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_handled ON threads(handled, received_at DESC);

CREATE TABLE IF NOT EXISTS experiments (
  id         TEXT PRIMARY KEY,
  name_en    TEXT NOT NULL, name_fa TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'running',
  metric     TEXT NOT NULL DEFAULT 'openRate',
  confidence REAL NOT NULL DEFAULT 0,
  auto_promote INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_variants (
  id            TEXT PRIMARY KEY,
  experiment_id TEXT NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  label         TEXT NOT NULL,
  text_en       TEXT NOT NULL, text_fa TEXT NOT NULL,
  split         INTEGER NOT NULL DEFAULT 50,
  sent          INTEGER NOT NULL DEFAULT 0,
  rate          REAL NOT NULL DEFAULT 0,
  winner        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS suppression (
  id         TEXT PRIMARY KEY,
  email      TEXT NOT NULL UNIQUE,
  reason     TEXT NOT NULL DEFAULT 'manual',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS domains (
  id         TEXT PRIMARY KEY,
  domain     TEXT NOT NULL UNIQUE,
  status     TEXT NOT NULL DEFAULT 'unverified',
  spf        INTEGER NOT NULL DEFAULT 0,
  dkim       INTEGER NOT NULL DEFAULT 0,
  dmarc      INTEGER NOT NULL DEFAULT 0,
  bimi       INTEGER NOT NULL DEFAULT 0,
  ip         TEXT NOT NULL DEFAULT 'shared',
  dedicated  INTEGER NOT NULL DEFAULT 0,
  reputation INTEGER NOT NULL DEFAULT 70,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dns_records (
  id        TEXT PRIMARY KEY,
  domain_id TEXT NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  type      TEXT NOT NULL,
  host      TEXT NOT NULL,
  value     TEXT NOT NULL,
  ok        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS integrations (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  category TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0,
  emoji   TEXT NOT NULL DEFAULT '',
  desc_en TEXT NOT NULL DEFAULT '', desc_fa TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kb_sources (
  id        TEXT PRIMARY KEY,
  name_en   TEXT NOT NULL, name_fa TEXT NOT NULL,
  type      TEXT NOT NULL DEFAULT 'file',
  chunks    INTEGER NOT NULL DEFAULT 0,
  status    TEXT NOT NULL DEFAULT 'indexed',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS brand_voice (
  id       INTEGER PRIMARY KEY CHECK (id = 1),
  axes     TEXT NOT NULL DEFAULT '[]',
  banned   TEXT NOT NULL DEFAULT '[]',
  notes    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS api_keys (
  id         TEXT PRIMARY KEY,
  name_en    TEXT NOT NULL, name_fa TEXT NOT NULL,
  prefix     TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  scopes     TEXT NOT NULL DEFAULT '[]',
  last_used_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
  id       TEXT PRIMARY KEY,
  url      TEXT NOT NULL,
  events   TEXT NOT NULL DEFAULT '[]',
  enabled  INTEGER NOT NULL DEFAULT 1,
  ok_rate  REAL NOT NULL DEFAULT 100,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
  id         TEXT PRIMARY KEY,
  webhook_id TEXT NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
  event      TEXT NOT NULL,
  status     INTEGER NOT NULL DEFAULT 200,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity (
  id        TEXT PRIMARY KEY,
  kind      TEXT NOT NULL DEFAULT 'system',
  actor     TEXT NOT NULL DEFAULT 'system',
  action_en TEXT NOT NULL, action_fa TEXT NOT NULL,
  target    TEXT NOT NULL DEFAULT '',
  tone      TEXT NOT NULL DEFAULT 'info',
  ip        TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_at ON activity(created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
  id       TEXT PRIMARY KEY,
  tone     TEXT NOT NULL DEFAULT 'info',
  title_en TEXT NOT NULL, title_fa TEXT NOT NULL,
  body_en  TEXT NOT NULL, body_fa TEXT NOT NULL,
  unread   INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id          TEXT PRIMARY KEY,
  type        TEXT NOT NULL,
  email       TEXT NOT NULL DEFAULT '',
  campaign_id TEXT REFERENCES campaigns(id) ON DELETE SET NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(created_at DESC);

CREATE TABLE IF NOT EXISTS recommendations (
  id        TEXT PRIMARY KEY,
  agent_id  TEXT REFERENCES agents(id) ON DELETE CASCADE,
  lift      REAL NOT NULL DEFAULT 0,
  effort    TEXT NOT NULL DEFAULT 'low',
  title_en  TEXT NOT NULL, title_fa TEXT NOT NULL,
  body_en   TEXT NOT NULL, body_fa TEXT NOT NULL,
  state     TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
  id        TEXT PRIMARY KEY,
  amount    REAL NOT NULL,
  status    TEXT NOT NULL DEFAULT 'paid',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_counters (
  id       INTEGER PRIMARY KEY CHECK (id = 1),
  emails_used INTEGER NOT NULL DEFAULT 0,
  emails_limit INTEGER NOT NULL DEFAULT 500000,
  credits_used INTEGER NOT NULL DEFAULT 0,
  credits_limit INTEGER NOT NULL DEFAULT 120000,
  contacts_limit INTEGER NOT NULL DEFAULT 100000,
  renews_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revoked    INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);
"""


def init_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA)
    # The deployment row owns its own DDL (see app/deployment.py) so the
    # white-label layer stays removable in one piece.
    from .budget import SCHEMA as BUDGET_SCHEMA
    from .mailer import SCHEMA as OUTBOX_SCHEMA
    from .prospect import SCHEMA as LEADS_SCHEMA
    from .routers.chats import SCHEMA as CHAT_SCHEMA
    from .routers.design import SCHEMA as ASSET_SCHEMA, migrate as migrate_templates
    from .deployment import SCHEMA as DEPLOYMENT_SCHEMA, ensure_row, migrate
    conn.executescript(DEPLOYMENT_SCHEMA)
    conn.executescript(BUDGET_SCHEMA)
    conn.executescript(ASSET_SCHEMA)
    conn.executescript(CHAT_SCHEMA)
    conn.executescript(OUTBOX_SCHEMA)
    conn.executescript(LEADS_SCHEMA)
    conn.commit()
    migrate()
    migrate_templates()
    ensure_row()


def reset_db() -> None:
    """Drop everything. Used by the test-suite between runs."""
    conn = connect()
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    conn.execute("PRAGMA foreign_keys = OFF")
    for t in tables:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db()
