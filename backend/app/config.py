"""Settings, read once from the environment.

Everything has a working default so `python run.py` starts a usable server with
no setup at all. The only value you should genuinely override in production is
`SECRET_KEY` — the default is derived per-machine and per-install, which is
fine for development and useless for a deployment behind a load balancer.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(key: str, default: str) -> str:
    value = os.environ.get(key, "").strip()
    return value or default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _default_secret() -> str:
    """A stable per-install secret, so tokens survive a restart in dev.

    Generated once into `.secret` next to the database rather than being a
    constant in the source: a hard-coded default key that ships in a repo is
    the single most common way a JWT implementation gets broken open.
    """
    path = BASE_DIR / ".secret"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = "MailPilot API"
    version: str = "1.0.0"

    # sqlite path; ":memory:" is used by the test-suite
    db_path: str = field(default_factory=lambda: _env("MAILPILOT_DB", str(BASE_DIR / "mailpilot.db")))

    secret_key: str = field(default_factory=lambda: _env("MAILPILOT_SECRET", "") or _default_secret())
    access_ttl_min: int = field(default_factory=lambda: _env_int("MAILPILOT_ACCESS_TTL_MIN", 60 * 12))
    refresh_ttl_days: int = field(default_factory=lambda: _env_int("MAILPILOT_REFRESH_TTL_DAYS", 30))

    # the Vite dev server, plus whatever the deployment adds
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env(
                "MAILPILOT_CORS",
                "http://localhost:4300,http://127.0.0.1:4300,http://localhost:4301,http://127.0.0.1:4301,http://localhost:5173",
            ).split(",")
            if o.strip()
        )
    )

    # The background sender. On by default; turn it off for a process that must
    # never put mail on the wire — the test-suite, a maintenance run, or a
    # second instance brought up beside a live one to look at the data.
    sender_enabled: bool = field(default_factory=lambda: _env_bool("MAILPILOT_SENDER", True))

    # Demo data is never written unless it is asked for by name.
    seed_demo_on_start: bool = field(default_factory=lambda: _env_bool("MAILPILOT_DEMO", False))
    docs: bool = field(default_factory=lambda: _env_bool("MAILPILOT_DOCS", True))

    # The origin this panel is reached at from OUTSIDE. Only Google OAuth needs
    # it: the redirect URI has to match the console entry byte for byte, and it
    # cannot be guessed from a request that arrived through a reverse proxy.
    public_url: str = field(default_factory=lambda: _env("MAILPILOT_PUBLIC_URL", "").rstrip("/"))

    demo_email: str = field(default_factory=lambda: _env("MAILPILOT_OWNER_EMAIL", "owner@example.com"))
    demo_password: str = field(default_factory=lambda: _env("MAILPILOT_OWNER_PASSWORD", "mailpilot"))


settings = Settings()
