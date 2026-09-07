"""What the business actually is, collected once.

Until now this product held its business knowledge in two places that did
not agree with each other. `deployment.agent_brief` was a paragraph the
implementer typed ("About business"), `deployment.agent_tone` was one word,
and `brand_voice` was four unlabelled 0-100 sliders plus a banned list.
Every prompt in the product read some mixture of them, and nothing said
which won. A customer could set a warm tone in one screen and a formal
slider in another and there was no answer to what the agent would do.

This is the single structured answer. It is what the email engine reads,
and it is filled in by the person who owns the business rather than by the
implementer who installed the panel.

WHY `confirmed` EXISTS. The wizard can have its answers suggested from the
customer's own website, and a suggestion must never quietly replace
something the customer typed. So every field the customer has actually
answered is recorded here by name; analysis may fill anything NOT in that
list and must leave everything in it alone. Without this the second
website analysis silently overwrites the first session's careful edits.

WHY THE LEGACY FIELDS SURVIVE. `agent_brief`, `agent_guardrails` and
`brand_voice` are still read as a fallback when this profile has nothing
to say, so a deployment that upgrades mid-flight keeps behaving the way it
did that morning. They are no longer the source of truth and are no longer
editable in the main UI; they are a floor, not a rival.
"""

from __future__ import annotations

from typing import Any

from . import db
from .domain import iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS brand_profile (
  id                     INTEGER PRIMARY KEY CHECK (id = 1),
  brand_name             TEXT NOT NULL DEFAULT '',
  website_url            TEXT NOT NULL DEFAULT '',
  business_summary       TEXT NOT NULL DEFAULT '',
  offers                 TEXT NOT NULL DEFAULT '[]',
  ideal_customer_profile TEXT NOT NULL DEFAULT '',
  customer_pain_points   TEXT NOT NULL DEFAULT '[]',
  customer_outcomes      TEXT NOT NULL DEFAULT '[]',
  differentiators        TEXT NOT NULL DEFAULT '[]',
  proof_points           TEXT NOT NULL DEFAULT '[]',
  preferred_cta          TEXT NOT NULL DEFAULT '',
  forbidden_claims       TEXT NOT NULL DEFAULT '[]',
  brand_voice            TEXT NOT NULL DEFAULT '[]',
  analysis               TEXT NOT NULL DEFAULT '{}',
  confirmed              TEXT NOT NULL DEFAULT '[]',
  current_step           INTEGER NOT NULL DEFAULT 1,
  completed              INTEGER NOT NULL DEFAULT 0,
  updated_at             TEXT NOT NULL DEFAULT ''
);
"""

#: Columns added after this table first shipped, with the DDL to add them.
#: Same idempotent pattern the deployment row uses: `CREATE TABLE IF NOT
#: EXISTS` is a no-op against a table that already exists, so a panel
#: installed before a column was added would otherwise fail on first read.
_ADDED_COLUMNS: dict[str, str] = {}

#: The twelve questions, in the order the wizard asks them. The wizard's
#: step number is an index into this, so the two can never disagree about
#: which question step 7 is.
QUESTIONS: list[dict[str, Any]] = [
    {"step": 1, "field": "brand_name", "kind": "text", "required": True},
    {"step": 2, "field": "website_url", "kind": "url", "required": False},
    {"step": 3, "field": "business_summary", "kind": "textarea", "required": True},
    {"step": 4, "field": "offers", "kind": "offers", "required": True},
    {"step": 5, "field": "ideal_customer_profile", "kind": "textarea", "required": True},
    {"step": 6, "field": "customer_pain_points", "kind": "list", "required": False},
    {"step": 7, "field": "customer_outcomes", "kind": "list", "required": True},
    {"step": 8, "field": "differentiators", "kind": "list", "required": False},
    {"step": 9, "field": "proof_points", "kind": "list", "required": False},
    {"step": 10, "field": "preferred_cta", "kind": "choice", "required": False},
    {"step": 11, "field": "forbidden_claims", "kind": "list", "required": False},
    {"step": 12, "field": "brand_voice", "kind": "tones", "required": True},
]
TOTAL_STEPS = len(QUESTIONS)

#: The twelve tones, multi-select. Values are stored; labels are the panel's
#: business. Kept here because the generator has to validate against them.
TONES = [
    "professional", "friendly", "premium_luxury", "direct", "warm", "executive",
    "technical", "minimal", "confident", "consultative", "formal", "casual",
]

#: What the reader can ask a recipient to do. "auto" lets the engine pick.
CTAS = ["reply", "meeting", "demo", "information", "link", "call", "auto"]

#: Fields stored as JSON lists rather than plain text.
_LIST_FIELDS = {
    "offers", "customer_pain_points", "customer_outcomes", "differentiators",
    "proof_points", "forbidden_claims", "brand_voice",
}
_TEXT_FIELDS = {
    "brand_name", "website_url", "business_summary", "ideal_customer_profile",
    "preferred_cta",
}
FIELDS = _LIST_FIELDS | _TEXT_FIELDS

#: What Beyondex Professional mode needs before it can write anything
#: worth sending. Short on purpose: a business with no website and no proof
#: can still run the mode, because neither is needed to say something true
#: and specific. Without these six it would be guessing.
REQUIRED_FOR_PRO = [
    "brand_name", "business_summary", "offers",
    "ideal_customer_profile", "customer_outcomes", "brand_voice",
]


def migrate() -> None:
    """Bring an existing profile row up to the current shape."""
    have = {r["name"] for r in db.query("PRAGMA table_info(brand_profile)")}
    if not have:
        return
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in have:
            db.execute(f"ALTER TABLE brand_profile ADD COLUMN {column} {ddl}")


def ensure_row() -> None:
    """A profile always exists, even before the wizard is opened."""
    if db.scalar("SELECT COUNT(*) FROM brand_profile WHERE id = 1", default=0):
        return
    db.insert("brand_profile", {"id": 1, "updated_at": iso()})


def get() -> dict[str, Any]:
    """The profile, with the JSON columns already decoded."""
    ensure_row()
    row = db.one("SELECT * FROM brand_profile WHERE id = 1")
    out: dict[str, Any] = {"id": 1}
    for field in _TEXT_FIELDS:
        out[field] = row[field] or ""
    for field in _LIST_FIELDS:
        out[field] = db.loads(row[field], [])
    out["analysis"] = db.loads(row["analysis"], {})
    out["confirmed"] = db.loads(row["confirmed"], [])
    out["current_step"] = row["current_step"]
    out["completed"] = bool(row["completed"])
    out["updated_at"] = row["updated_at"] or ""
    return out


def save(patch: dict[str, Any], *, confirm: bool = True) -> dict[str, Any]:
    """Write some answers. Returns the whole profile.

    `confirm` is what separates the customer answering a question from the
    website analysis proposing an answer. A confirmed field is one the
    customer has decided, and analysis is not allowed to touch it again.
    """
    ensure_row()
    current = get()
    data: dict[str, Any] = {"updated_at": iso()}
    confirmed = set(current["confirmed"])

    for field, value in patch.items():
        if field in _TEXT_FIELDS:
            data[field] = str(value or "")[:4000]
        elif field in _LIST_FIELDS:
            data[field] = db.dumps(_clean_list(field, value))
        elif field == "current_step":
            data["current_step"] = max(1, min(int(value or 1), TOTAL_STEPS))
        elif field == "completed":
            data["completed"] = 1 if value else 0
        elif field == "analysis":
            data["analysis"] = db.dumps(value or {})
        else:
            continue
        if confirm and field in FIELDS:
            confirmed.add(field)

    data["confirmed"] = db.dumps(sorted(confirmed))
    with db.transaction():
        db.update("brand_profile", 1, data)
    return get()


def _clean_list(field: str, value: Any) -> list:
    """Normalise a list field, dropping empties and capping length."""
    if not isinstance(value, list):
        return []
    if field == "offers":
        out = []
        for item in value[:20]:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()[:200]
                desc = str(item.get("description") or "").strip()[:1000]
            else:
                name, desc = str(item).strip()[:200], ""
            if name:
                out.append({"name": name, "description": desc})
        return out
    if field == "proof_points":
        out = []
        for item in value[:20]:
            if isinstance(item, dict):
                kind = str(item.get("kind") or "result").strip()[:40]
                text = str(item.get("text") or "").strip()[:1000]
            else:
                kind, text = "result", str(item).strip()[:1000]
            if text:
                out.append({"kind": kind, "text": text})
        return out
    if field == "brand_voice":
        # Only tones this product actually knows about. An unknown string
        # here would reach the generator as an instruction nobody wrote.
        return [t for t in dict.fromkeys(str(v) for v in value) if t in TONES][:12]
    return [str(v).strip()[:500] for v in value[:20] if str(v).strip()]


def answered(profile: dict[str, Any], field: str) -> bool:
    """Has this field got a real answer in it?"""
    value = profile.get(field)
    if isinstance(value, list):
        return len(value) > 0
    return bool(str(value or "").strip())


def completeness(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """How much of the profile is filled in, and whether pro mode may run.

    The percentage counts every question, so the reader sees progress for
    answering an optional one. The gate counts only the six that the
    generator genuinely cannot work without, so an optional question can
    never be the thing standing between them and sending.
    """
    p = profile or get()
    done = [q["field"] for q in QUESTIONS if answered(p, q["field"])]
    missing = [f for f in REQUIRED_FOR_PRO if not answered(p, f)]
    return {
        "answered": len(done),
        "total": TOTAL_STEPS,
        "percent": round(len(done) / TOTAL_STEPS * 100),
        "complete": len(done) == TOTAL_STEPS,
        "proReady": not missing,
        "missingForPro": missing,
    }


def as_prompt(profile: dict[str, Any] | None = None) -> str:
    """The profile as the generator should read it.

    Written as prose with headings rather than dumped as JSON: the model
    follows "never say" far more reliably as a sentence than as a key in an
    object, and the forbidden list is the part that must not be missed.
    """
    p = profile or get()
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        if isinstance(value, list):
            if not value:
                return
            lines.append(f"{label}:")
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("kind") or ""
                    body = item.get("description") or item.get("text") or ""
                    lines.append(f"  - {name}: {body}" if name and body else f"  - {name or body}")
                else:
                    lines.append(f"  - {item}")
        elif str(value or "").strip():
            lines.append(f"{label}: {value}")

    add("The business", p.get("brand_name"))
    add("Website", p.get("website_url"))
    add("What it does", p.get("business_summary"))
    add("What it sells", p.get("offers"))
    add("Its ideal customer", p.get("ideal_customer_profile"))
    add("Problems it solves", p.get("customer_pain_points"))
    add("Outcomes customers get", p.get("customer_outcomes"))
    add("Why choose it over alternatives", p.get("differentiators"))
    add("Proof it may cite", p.get("proof_points"))

    cta = p.get("preferred_cta") or ""
    if cta and cta != "auto":
        add("Preferred call to action", cta)

    tones = p.get("brand_voice") or []
    if tones:
        lines.append("Brand voice: " + ", ".join(tones))
        lines.append("Blend these tones coherently. Do not force every tone into "
                     "every sentence, and never let tone cost clarity or truth.")

    forbidden = p.get("forbidden_claims") or []
    if forbidden:
        lines.append("")
        lines.append("NEVER, under any circumstances, do any of the following:")
        for rule in forbidden:
            lines.append(f"  - {rule}")

    proof = p.get("proof_points") or []
    if not proof:
        lines.append("")
        lines.append("This business has given NO proof points. Do not cite results, "
                     "client names, case studies or numbers of any kind.")

    return "\n".join(lines)
