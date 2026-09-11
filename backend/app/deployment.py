"""What makes one installation of this agent different from another.

This product is sold as a finished agent, not as a platform. The team that
implements it configures a deployment once — branding, which sections the
customer is allowed to see, the OpenAI key it runs on, who the agent is — and
the customer never sees any of that machinery.

Everything lives in a single row (`deployment`, id = 1), because there is
exactly one deployment per install. The alternative — a settings table of
key/value pairs — reads well until you need a default, a type, or a migration,
and then it reads badly forever.

Two rules hold this together:

  * `public_config()` is served WITHOUT authentication, because the sign-in
    screen has to be branded before anyone has signed in. It must therefore
    never contain a secret. The API key is write-only from the outside: it goes
    in through the wizard and comes back out only as a masked hint.

  * `MODULES` is the single source of truth for what a deployment includes.
    Turning a module off hides its navigation AND refuses its endpoints, so a
    customer who was not sold billing cannot reach billing by typing the URL.
"""

from __future__ import annotations

import json
from typing import Any

from . import db
from .ai_provider import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_REASONING,
    HARD_MAX_TOKENS,
    MODEL_VALUES,
    REASONING,
    AISettings,
)

# Every optional section of the panel. `core` modules cannot be switched off —
# an email agent with no campaigns is not a smaller product, it is a broken one.
MODULES: list[dict[str, Any]] = [
    {"id": "campaigns", "core": True, "en": "Campaigns", "fa": "کمپین‌ها",
     "note_en": "What the agent has sent and plans to send", "note_fa": "آنچه ایجنت فرستاده و در برنامه دارد"},
    {"id": "audience", "core": True, "en": "Audience", "fa": "مخاطبان",
     "note_en": "Contacts, groups and the do-not-contact list", "note_fa": "مخاطبان، گروه‌ها و فهرست تماس‌ممنوع"},
    {"id": "inbox", "core": False, "en": "Replies", "fa": "پاسخ‌ها",
     "note_en": "Incoming replies the agent triages", "note_fa": "پاسخ‌های ورودی که ایجنت دسته‌بندی می‌کند"},
    {"id": "templates", "core": False, "en": "Email designer", "fa": "طراح ایمیل",
     "note_en": "Build reusable HTML email templates from images and facts",
     "note_fa": "ساخت قالب HTML ایمیل از تصویر و اطلاعات، برای استفادهٔ دوباره"},
    {"id": "insights", "core": False, "en": "Insights", "fa": "بینش‌ها",
     "note_en": "Open and click reporting", "note_fa": "گزارش بازشدن و کلیک"},
    {"id": "billing", "core": False, "en": "Billing", "fa": "صورت‌حساب",
     "note_en": "Plan, usage meters and invoices", "note_fa": "طرح، مصرف و فاکتورها"},
    {"id": "team", "core": False, "en": "Team", "fa": "تیم",
     "note_en": "Extra seats and roles", "note_fa": "کاربران و نقش‌ها"},
    {"id": "domains", "core": False, "en": "Sending domains", "fa": "دامنه‌های ارسال",
     "note_en": "DNS records and sender verification", "note_fa": "رکوردهای DNS و تأیید فرستنده"},
    {"id": "integrations", "core": False, "en": "Integrations", "fa": "یکپارچه‌سازی‌ها",
     "note_en": "Shop, CRM and analytics connections", "note_fa": "اتصال فروشگاه، CRM و تحلیل"},
    {"id": "developers", "core": False, "en": "Developer API", "fa": "API توسعه‌دهنده",
     "note_en": "API keys and webhooks for the customer's own engineers",
     "note_fa": "کلیدهای API و وب‌هوک برای مهندسان مشتری"},
]
CORE_MODULES = {m["id"] for m in MODULES if m["core"]}
ALL_MODULES = {m["id"] for m in MODULES}
# Out of the box: the five that make an email agent, and nothing else. The
# reporting section and the developer API are things a deployment adds on
# purpose, because each one puts another entry in a navigation whose whole
# point is being short.
DEFAULT_MODULES = sorted(ALL_MODULES - {"developers", "insights"})

TONES = ["warm", "direct", "playful", "formal"]

#: Shown on the connect screen, so the customer reads what they are granting in
#: the panel's words before they read it in Google's.
GOOGLE_SCOPES = ["gmail.send", "gmail.readonly", "userinfo.email"]
AUTONOMY = ["suggest", "approve", "auto"]

DEFAULTS: dict[str, Any] = {
    "brand_name": "MailPilot",
    "brand_tagline": "AI email marketing",
    "accent": "#7ba3cd",
    "support_email": "",
    "default_lang": "en",
    "locked_lang": 0,
    "modules": DEFAULT_MODULES,
    "ai_key": "",
    "ai_model": DEFAULT_MODEL,
    "ai_search": 1,
    "ai_reasoning": DEFAULT_REASONING,
    "ai_max_tokens": DEFAULT_MAX_TOKENS,
    "ai_daily_cap": 0,
    "ai_monthly_cap": 0,
    "from_name": "",
    "from_email": "",
    "reply_to": "",
    "agent_name": "Nova",
    "agent_role": "Email marketing manager",
    "agent_tone": "warm",
    "agent_autonomy": "approve",
    "agent_brief": "",
    "agent_guardrails": "",
    "voice_axes": 1,
    "setup_complete": 0,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS deployment (
  id                INTEGER PRIMARY KEY CHECK (id = 1),
  brand_name        TEXT NOT NULL DEFAULT 'MailPilot',
  brand_tagline     TEXT NOT NULL DEFAULT '',
  accent            TEXT NOT NULL DEFAULT '#7ba3cd',
  support_email     TEXT NOT NULL DEFAULT '',
  default_lang      TEXT NOT NULL DEFAULT 'en',
  locked_lang       INTEGER NOT NULL DEFAULT 0,
  modules           TEXT NOT NULL DEFAULT '[]',
  ai_key            TEXT NOT NULL DEFAULT '',
  ai_model          TEXT NOT NULL DEFAULT 'gpt-4o-mini',
  ai_search         INTEGER NOT NULL DEFAULT 1,
  ai_reasoning      TEXT NOT NULL DEFAULT 'low',
  ai_max_tokens     INTEGER NOT NULL DEFAULT 2000,
  ai_daily_cap      INTEGER NOT NULL DEFAULT 0,
  ai_monthly_cap    INTEGER NOT NULL DEFAULT 0,
  from_name         TEXT NOT NULL DEFAULT '',
  from_email        TEXT NOT NULL DEFAULT '',
  reply_to          TEXT NOT NULL DEFAULT '',
  agent_name        TEXT NOT NULL DEFAULT 'Nova',
  agent_role        TEXT NOT NULL DEFAULT '',
  agent_tone        TEXT NOT NULL DEFAULT 'warm',
  agent_autonomy    TEXT NOT NULL DEFAULT 'approve',
  agent_brief       TEXT NOT NULL DEFAULT '',
  agent_guardrails  TEXT NOT NULL DEFAULT '',
  voice_axes        INTEGER NOT NULL DEFAULT 1,
  setup_complete    INTEGER NOT NULL DEFAULT 0,
  google_client_id  TEXT NOT NULL DEFAULT '',
  google_secret     TEXT NOT NULL DEFAULT '',
  google_refresh    TEXT NOT NULL DEFAULT '',
  google_email      TEXT NOT NULL DEFAULT '',
  google_state      TEXT NOT NULL DEFAULT '',
  google_connected_at TEXT NOT NULL DEFAULT '',
  google_sync_at    TEXT NOT NULL DEFAULT '',
  updated_at        TEXT NOT NULL DEFAULT ''
);
"""


#: columns added after the first release, with the DDL to add them
_ADDED_COLUMNS = {
    "ai_reasoning": "TEXT NOT NULL DEFAULT 'low'",
    "ai_max_tokens": "INTEGER NOT NULL DEFAULT 2000",
    "ai_daily_cap": "INTEGER NOT NULL DEFAULT 0",
    "google_client_id": "TEXT NOT NULL DEFAULT ''",
    "google_secret": "TEXT NOT NULL DEFAULT ''",
    "google_refresh": "TEXT NOT NULL DEFAULT ''",
    "google_email": "TEXT NOT NULL DEFAULT ''",
    "google_state": "TEXT NOT NULL DEFAULT ''",
    "google_connected_at": "TEXT NOT NULL DEFAULT ''",
    "google_sync_at": "TEXT NOT NULL DEFAULT ''",
    "voice_axes": "INTEGER NOT NULL DEFAULT 1",
    # Sender-health thresholds, as JSON. Empty means "use the defaults in
    # senderhealth.DEFAULTS" -- there is no universally safe bounce rate,
    # so a deployment that knows its own numbers can say so.
    "health_thresholds": "TEXT NOT NULL DEFAULT '{}'",
}


def migrate() -> None:
    """Bring an existing deployment row up to the current shape.

    `CREATE TABLE IF NOT EXISTS` is a no-op against a table that already exists,
    so a panel installed before these columns were added would keep running on
    the old shape and fail on first read. Adding them is cheap and idempotent.
    """
    have = {r["name"] for r in db.query("PRAGMA table_info(deployment)")}
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in have:
            db.execute(f"ALTER TABLE deployment ADD COLUMN {column} {ddl}")


def ensure_row() -> None:
    """A deployment always exists, even before the wizard is opened — the login
    screen reads it, and that happens first."""
    if db.scalar("SELECT COUNT(*) FROM deployment WHERE id = 1", default=0):
        return
    db.insert("deployment", {
        "id": 1,
        "brand_name": DEFAULTS["brand_name"],
        "brand_tagline": DEFAULTS["brand_tagline"],
        "accent": DEFAULTS["accent"],
        "modules": json.dumps(DEFAULT_MODULES),
        "ai_model": DEFAULT_MODEL,
        "agent_name": DEFAULTS["agent_name"],
        "agent_role": DEFAULTS["agent_role"],
        "agent_tone": DEFAULTS["agent_tone"],
        "agent_autonomy": DEFAULTS["agent_autonomy"],
        "updated_at": "",
    })


def get() -> dict[str, Any]:
    ensure_row()
    row = db.one("SELECT * FROM deployment WHERE id = 1")
    out = dict(row) if row else dict(DEFAULTS)
    out["modules"] = _modules(out.get("modules"))
    return out


def _modules(raw: Any) -> list[str]:
    """Core modules are always present, whatever is stored — a row written by an
    older build, or by hand, cannot switch off campaigns."""
    try:
        picked = set(json.loads(raw)) if isinstance(raw, str) else set(raw or [])
    except (json.JSONDecodeError, TypeError):
        picked = set(DEFAULT_MODULES)
    return sorted((picked & ALL_MODULES) | CORE_MODULES)


def enabled(module: str) -> bool:
    return module in get()["modules"]


def ai_settings() -> AISettings:
    d = get()
    return AISettings(
        key=d.get("ai_key") or "",
        # A deployment configured before the catalogue changed still has the
        # old id stored. Falling back beats sending a model that no longer
        # exists and failing every request with a 404 from the provider.
        model=d.get("ai_model") if d.get("ai_model") in MODEL_VALUES else DEFAULT_MODEL,
        search_enabled=bool(d.get("ai_search")),
        reasoning=d.get("ai_reasoning") or DEFAULT_REASONING,
        max_tokens=int(d.get("ai_max_tokens") or DEFAULT_MAX_TOKENS),
    )


def caps() -> tuple[int, int]:
    """(daily, monthly) token budgets. Zero means unlimited."""
    d = get()
    return int(d.get("ai_daily_cap") or 0), int(d.get("ai_monthly_cap") or 0)


def mask(key: str) -> str:
    """Enough to recognise which key is installed, useless if intercepted."""
    if not key:
        return ""
    return f"sk-…{key[-4:]}" if len(key) > 8 else "sk-…"


def public_config() -> dict[str, Any]:
    """Served unauthenticated to brand the sign-in screen.

    Nothing here may be a secret. `ai.configured` is a boolean rather than a
    masked key precisely because this response is world-readable.
    """
    d = get()
    return {
        "brand": {
            "name": d["brand_name"],
            "tagline": d["brand_tagline"],
            "accent": d["accent"],
            "supportEmail": d["support_email"],
        },
        "lang": {"default": d["default_lang"], "locked": bool(d["locked_lang"])},
        "modules": d["modules"],
        "agent": {"name": d["agent_name"], "role": d["agent_role"]},
        "ai": {"configured": bool(d["ai_key"]), "search": bool(d["ai_search"])},
        "voiceAxes": bool(d.get("voice_axes", 1)),
        "setupComplete": bool(d["setup_complete"]),
    }


def owner_config() -> dict[str, Any]:
    """Everything the wizard needs to re-open on an existing deployment."""
    d = get()
    out = public_config()
    out["sending"] = {"fromName": d["from_name"], "fromEmail": d["from_email"], "replyTo": d["reply_to"]}
    out["agent"] = {
        "name": d["agent_name"], "role": d["agent_role"], "tone": d["agent_tone"],
        "autonomy": d["agent_autonomy"], "brief": d["agent_brief"], "guardrails": d["agent_guardrails"],
        "voiceAxes": bool(d.get("voice_axes", 1)),
    }
    out["ai"] = {
        "configured": bool(d["ai_key"]), "keyHint": mask(d["ai_key"]),
        "model": d["ai_model"] if d["ai_model"] in MODEL_VALUES else DEFAULT_MODEL,
        "search": bool(d["ai_search"]),
        "reasoning": d.get("ai_reasoning") or DEFAULT_REASONING,
        "maxTokens": d.get("ai_max_tokens") or DEFAULT_MAX_TOKENS,
        "dailyCap": d.get("ai_daily_cap") or 0,
        "monthlyCap": d["ai_monthly_cap"],
        "hardMaxTokens": HARD_MAX_TOKENS,
    }
    from . import budget

    daily, monthly = caps()
    out["usage"] = budget.snapshot(daily, monthly)
    out["google"] = google_status()
    out["catalog"] = {"modules": MODULES, "tones": TONES, "autonomy": AUTONOMY,
                      "reasoning": REASONING}
    return out


def google_status() -> dict[str, Any]:
    """What the panel may know about the connected mailbox.

    The refresh token is the whole credential and it is not in here. Neither is
    the client secret — `hasSecret` is a boolean for exactly the same reason
    `ai.configured` is: the caller needs to know whether to ask for one, not
    what it is.
    """
    d = get()
    mailbox = (d.get("google_email") or "").strip().lower()
    sender = (d.get("from_email") or "").strip().lower()
    return {
        "connected": bool(d.get("google_refresh")),
        "email": d.get("google_email") or "",
        "connectedAt": d.get("google_connected_at") or "",
        "clientId": d.get("google_client_id") or "",
        "hasSecret": bool(d.get("google_secret")),
        "scopes": GOOGLE_SCOPES,
        "fromEmail": d.get("from_email") or "",
        # Gmail rejects a From it does not own. Reported rather than enforced:
        # an alias verified in Gmail under "Send mail as" is legitimate and we
        # cannot see from here whether they have set one up.
        "fromMismatch": bool(mailbox and sender and sender != mailbox),
    }


def save_google(**fields: Any) -> None:
    """Write Gmail columns without going through `save()`.

    Separate on purpose: `save()` is the wizard's payload parser and everything
    in it arrives from a browser. These values arrive from Google, or are being
    cleared, and none of them should be settable by the same loose dict.
    """
    allowed = {"google_client_id", "google_secret", "google_refresh", "google_email",
               "google_state", "google_connected_at", "google_sync_at"}
    data = {k: v for k, v in fields.items() if k in allowed}
    if data:
        ensure_row()
        db.update("deployment", "1", data)


def save(payload: dict[str, Any]) -> dict[str, Any]:
    """Write the wizard's answers.

    Partial by design: the wizard saves each step as it is completed, so an
    interrupted setup resumes where it stopped instead of starting over.
    """
    ensure_row()
    data: dict[str, Any] = {}

    brand = payload.get("brand") or {}
    for src, col in (("name", "brand_name"), ("tagline", "brand_tagline"),
                     ("accent", "accent"), ("supportEmail", "support_email")):
        if src in brand:
            data[col] = str(brand[src] or "").strip()

    lang = payload.get("lang") or {}
    if "default" in lang:
        data["default_lang"] = "fa" if lang["default"] == "fa" else "en"
    if "locked" in lang:
        data["locked_lang"] = 1 if lang["locked"] else 0

    if "modules" in payload:
        data["modules"] = json.dumps(_modules(payload["modules"]))

    ai = payload.get("ai") or {}
    # An empty string means "leave the installed key alone"; clearing it is an
    # explicit act so a half-filled wizard step cannot silently disable the AI.
    if ai.get("key"):
        data["ai_key"] = str(ai["key"]).strip()
    if ai.get("clearKey"):
        data["ai_key"] = ""
    if ai.get("model") in MODEL_VALUES:
        data["ai_model"] = ai["model"]
    if "search" in ai:
        data["ai_search"] = 1 if ai["search"] else 0
    if ai.get("reasoning") in REASONING:
        data["ai_reasoning"] = ai["reasoning"]
    # Every budget field is clamped on the way in. `maxTokens` in particular can
    # never be raised past the hard ceiling, whatever is posted.
    for src, col, ceiling in (("maxTokens", "ai_max_tokens", HARD_MAX_TOKENS),
                              ("dailyCap", "ai_daily_cap", None),
                              ("monthlyCap", "ai_monthly_cap", None)):
        if src in ai:
            try:
                value = max(0, int(ai[src] or 0))
            except (TypeError, ValueError):
                continue
            if ceiling is not None:
                value = min(value or ceiling, ceiling)
            data[col] = value

    sending = payload.get("sending") or {}
    for src, col in (("fromName", "from_name"), ("fromEmail", "from_email"), ("replyTo", "reply_to")):
        if src in sending:
            data[col] = str(sending[src] or "").strip()

    agent = payload.get("agent") or {}
    if "name" in agent:
        data["agent_name"] = str(agent["name"] or "").strip() or DEFAULTS["agent_name"]
    if "role" in agent:
        data["agent_role"] = str(agent["role"] or "").strip()
    if agent.get("tone") in TONES:
        data["agent_tone"] = agent["tone"]
    if agent.get("autonomy") in AUTONOMY:
        data["agent_autonomy"] = agent["autonomy"]
    if "brief" in agent:
        data["agent_brief"] = str(agent["brief"] or "").strip()
    if "guardrails" in agent:
        data["agent_guardrails"] = str(agent["guardrails"] or "").strip()
    if "voiceAxes" in agent:
        data["voice_axes"] = 1 if agent["voiceAxes"] else 0

    if "setupComplete" in payload:
        data["setup_complete"] = 1 if payload["setupComplete"] else 0

    if data:
        from .domain import iso
        data["updated_at"] = iso()
        db.update("deployment", "1", data)
    return owner_config()


def agent_persona() -> str:
    """The system prompt every AI call in this product is built on.

    Assembled from the wizard's answers rather than hard-coded, so the agent a
    customer talks to is the one their implementer described — including the
    guardrails, which are stated as rules the model must not break.
    """
    from . import brandprofile

    d = get()
    profile = brandprofile.get()
    lines = [
        f"You are {d['agent_name']}, {d['agent_role'] or 'an email marketing manager'} "
        f"working inside {profile.get('brand_name') or d['brand_name']}.",
        "You write marketing email for a real business. Be concrete and specific.",
        "Never invent statistics, prices, dates or product names that you were not given.",
        "Never write subject lines in ALL CAPS and never use more than one exclamation mark.",
    ]

    # The Brand Information profile is the source of truth. The old
    # `agent_tone` / `agent_brief` / `agent_guardrails` fields are a FLOOR,
    # used only where the profile has nothing to say — so a deployment that
    # upgrades mid-morning keeps behaving the way it did that morning, and
    # a profile that has been filled in is never contradicted by a leftover
    # word in a field nobody can see any more.
    described = brandprofile.as_prompt(profile)
    if described.strip():
        lines += ["", "What you know about this business:", described]
    else:
        if d["agent_tone"]:
            lines.append(f"Your writing tone is {d['agent_tone']}.")
        if d["agent_brief"]:
            lines.append(f"What this business does, in their own words: {d['agent_brief']}")

    # Guardrails typed into the old Agent settings still bind. They are
    # additional to the profile's forbidden claims, never a replacement:
    # dropping a rule someone wrote is the one failure mode that cannot be
    # noticed from the outside.
    if d["agent_guardrails"]:
        lines.append(f"Hard rules you must never break: {d['agent_guardrails']}")
    return "\n".join(lines)
