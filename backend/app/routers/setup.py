"""The implementer's wizard.

These routes belong to the team that DEPLOYS the agent, not to the customer who
uses it. They are the only place where branding, module visibility and the
OpenAI key can be changed, and they are all owner-gated except the first.

`GET /config` is deliberately public. The sign-in screen is the first thing a
customer sees and it has to carry their own brand, which means it must render
before anyone has a token. `public_config()` is built to hold nothing secret.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import db, deployment
from ..ai_provider import MODELS, AIUnavailable, verify
from ..deps import Principal, current_user, requires
from ..domain import iso, log
from ..schemas import Body

router = APIRouter(tags=["setup"])


class SetupIn(Body):
    """Deliberately loose.

    The wizard saves one step at a time, so almost every request is a partial
    document. `deployment.save()` validates and ignores per field, which keeps
    an unknown key from rejecting an otherwise good step.
    """
    brand: dict | None = None
    lang: dict | None = None
    modules: list[str] | None = None
    ai: dict | None = None
    sending: dict | None = None
    agent: dict | None = None
    setupComplete: bool | None = None


class KeyIn(Body):
    key: str = ""
    model: str = ""


@router.get("/config")
def config() -> dict:
    """Public. Branding, enabled modules, and whether AI is configured."""
    return deployment.public_config()


@router.get("/setup")
def read_setup(_: Principal = Depends(requires("settings.write"))) -> dict:
    return deployment.owner_config()


@router.put("/setup")
def write_setup(payload: SetupIn, principal: Principal = Depends(requires("settings.write"))) -> dict:
    body = payload.model_dump(exclude_none=True)
    out = deployment.save(body)
    log(kind="human", actor=principal.id, action_en="updated the deployment setup",
        action_fa="تنظیمات استقرار را به‌روزرسانی کرد", target="deployment", tone="info")
    return out


@router.post("/setup/verify-key")
def verify_key(payload: KeyIn, _: Principal = Depends(requires("settings.write"))) -> dict:
    """Prove the key works before the panel is handed over.

    Falls back to the key already installed, so an owner re-checking an existing
    deployment does not have to paste their key again to test it.
    """
    key = payload.key.strip() or deployment.get().get("ai_key") or ""
    model = payload.model.strip() or deployment.get().get("ai_model") or ""
    if not key:
        raise HTTPException(status_code=400, detail="No API key to check")
    try:
        return verify(key, model)
    except AIUnavailable as exc:
        # A bad key is the operator's mistake, not a server fault — 400 so the
        # wizard shows the provider's own words instead of a generic failure
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/setup/models")
def models(_: Principal = Depends(requires("settings.write"))) -> dict:
    # Every list the wizard renders a picker from. `reasoning` was missing,
    # which left that Select with no options — present, and unusable.
    return {"models": MODELS, "modules": deployment.MODULES,
            "tones": deployment.TONES, "autonomy": deployment.AUTONOMY,
            "reasoning": deployment.REASONING}


@router.post("/setup/wipe-demo", status_code=200)
def wipe_demo(principal: Principal = Depends(requires("settings.write"))) -> dict:
    """Empty every operational table, keeping the deployment and its people.

    This is the button the implementer presses after showing a demo and before
    handing the panel over. Users, the deployment row and the brand voice
    survive; everything that would look like someone else's data does not.
    """
    tables = [
        "campaigns", "contacts", "segments", "suppression", "threads",
        "experiments", "experiment_variants", "journeys", "journey_steps",
        "templates", "kb_sources", "events", "activity", "notifications",
        "recommendations", "invoices", "webhook_deliveries", "domains",
        "dns_records", "api_keys", "webhooks",
    ]
    cleared = {}
    with db.transaction():
        for table in tables:
            before = db.scalar(f"SELECT COUNT(*) FROM {table}", default=0)
            db.execute(f"DELETE FROM {table}")
            if before:
                cleared[table] = before
        db.execute(
            "UPDATE usage_counters SET emails_used = 0, credits_used = 0, renews_at = ? WHERE id = 1",
            (iso(),),
        )
        db.execute("UPDATE integrations SET enabled = 0")
    log(kind="human", actor=principal.id, action_en="cleared all demo data",
        action_fa="همهٔ داده‌های نمایشی را پاک کرد", target="workspace", tone="warn")
    return {"ok": True, "cleared": cleared, "rows": sum(cleared.values())}


@router.post("/setup/complete")
def complete(principal: Principal = Depends(requires("settings.write"))) -> dict:
    """Mark the deployment ready. The wizard stops greeting on next load."""
    out = deployment.save({"setupComplete": True})
    log(kind="human", actor=principal.id, action_en="finished the deployment setup",
        action_fa="راه‌اندازی استقرار را کامل کرد", target="deployment", tone="good")
    return out


@router.post("/setup/reopen")
def reopen(_: Principal = Depends(requires("settings.write"))) -> dict:
    """Let an owner walk the wizard again without wiping anything.

    `settings.write`, like every other route in this file. It took only
    `current_user`, so any signed-in role — a viewer included — could flip
    `setupComplete` back to false and change what the whole panel shows to
    everybody. The docstring said "an owner"; the code did not.
    """
    return deployment.save({"setupComplete": False})
