"""Workspace administration: team, billing, domains, developers, settings,
integrations, templates, the brand brain, activity and notifications.

One rule runs through all of it: a workspace must never be left without an
owner. Every path that could remove the last one — deleting a member, changing
a role — checks first and refuses.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import db
from ..deps import Principal, client_ip, current_principal, current_user, module_enabled, requires
from ..domain import bi_in, iso, like, log, paginate
from ..emailhtml import sanitize
from ..schemas import (
    ApiKeyIn,
    BrandVoiceIn,
    DomainIn,
    IntegrationPatch,
    InviteIn,
    KbSourceIn,
    RolePatch,
    SettingsPatch,
    TemplateIn,
    WebhookIn,
    WebhookPatch,
)
from ..security import hash_password, new_api_key, new_id
from ..serial import activity as ser_activity
from ..serial import api_key as ser_key
from ..serial import domain_row as ser_domain
from ..serial import integration as ser_integration
from ..serial import invoice as ser_invoice
from ..serial import kb_source as ser_kb
from ..serial import notification as ser_notif
from ..serial import template as ser_template
from ..serial import user as ser_user
from ..serial import webhook as ser_webhook

def _needs(module: str):
    """Refuse a section this deployment was not sold."""
    return Depends(module_enabled(module))


router = APIRouter(tags=["workspace"])


# ================================================================ team


def _owner_count() -> int:
    return db.scalar("SELECT COUNT(*) FROM users WHERE role = 'owner' AND status = 'active'", default=0)


@router.get("/team")
def list_team(_: Principal = Depends(current_user)) -> list[dict]:
    return [ser_user(r) for r in db.query("SELECT * FROM users ORDER BY role, name_en")]


@router.post("/team", status_code=201, dependencies=[_needs("team")])
def invite(payload: InviteIn, principal: Principal = Depends(requires("team.invite"))) -> dict:
    email = str(payload.email).lower()
    if db.one("SELECT 1 FROM users WHERE lower(email) = ?", (email,)):
        raise HTTPException(status_code=409, detail="That address is already on the team")
    uid = new_id("u")
    name = payload.name or email.split("@")[0]
    with db.transaction():
        db.insert("users", {
            "id": uid, "email": email, **bi_in(name, "name"), "role": payload.role,
            # invited, not yet activated: no password means no way in until
            # the invitation is accepted
            "password_hash": "", "status": "pending",
            "last_active_at": None, "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en=f"invited {email}",
            action_fa=f"{email} را دعوت کرد", target=uid, tone="info")
    return ser_user(db.one("SELECT * FROM users WHERE id = ?", (uid,)))


@router.patch("/team/{user_id}", dependencies=[_needs("team")])
def change_role(user_id: str, payload: RolePatch, principal: Principal = Depends(requires("team.invite"))) -> dict:
    row = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if row["role"] == "owner" and payload.role != "owner" and _owner_count() <= 1:
        raise HTTPException(status_code=409, detail="A workspace must keep at least one owner")
    if payload.role == "owner" and principal.role != "owner":
        raise HTTPException(status_code=403, detail="Only an owner can promote someone to owner")
    with db.transaction():
        db.update("users", user_id, {"role": payload.role})
        log(kind="human", actor=principal.id, action_en=f"changed a role to {payload.role}",
            action_fa=f"نقشی را به {payload.role} تغییر داد", target=user_id, tone="info")
    return ser_user(db.one("SELECT * FROM users WHERE id = ?", (user_id,)))


@router.delete("/team/{user_id}", status_code=204, dependencies=[_needs("team")])
def remove_member(user_id: str, principal: Principal = Depends(requires("team.invite"))) -> None:
    row = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if row["role"] == "owner" and _owner_count() <= 1:
        raise HTTPException(status_code=409, detail="A workspace must keep at least one owner")
    if user_id == principal.id:
        raise HTTPException(status_code=409, detail="You cannot remove yourself")
    with db.transaction():
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        log(kind="human", actor=principal.id, action_en="removed a team member",
            action_fa="یک عضو تیم را حذف کرد", target=user_id, tone="warn")


# ================================================================ settings


def _workspace():
    row = db.one("SELECT * FROM workspaces LIMIT 1")
    if row is None:
        raise HTTPException(status_code=500, detail="Workspace missing — run the seeder")
    return row


@router.get("/settings")
def get_settings(_: Principal = Depends(current_principal)) -> dict:
    w = _workspace()
    return {
        "id": w["id"], "name": w["name"], "plan": w["plan"], "timezone": w["timezone"],
        "defaultLang": w["default_lang"],
        "sending": {"fromName": w["from_name"], "fromEmail": w["from_email"],
                    "replyTo": w["reply_to"], "footer": w["footer"],
                    "throttlePerHour": w["throttle_per_hour"],
                    "quietHours": bool(w["quiet_hours"]),
                    "quietFrom": w["quiet_from"], "quietTo": w["quiet_to"]},
        "ai": {"defaultModel": w["default_model"], "creativity": w["creativity"],
               "autoApprove": bool(w["auto_approve"])},
        "privacy": {"gdpr": bool(w["gdpr"]), "retentionMonths": w["retention_months"]},
        "notif": db.loads(w["notif"], {}),
    }


@router.patch("/settings")
def update_settings(payload: SettingsPatch, principal: Principal = Depends(requires("settings.write"))) -> dict:
    w = _workspace()
    cols = {
        "name": "name", "timezone": "timezone", "default_lang": "default_lang",
        "from_name": "from_name", "from_email": "from_email", "reply_to": "reply_to",
        "footer": "footer", "throttle_per_hour": "throttle_per_hour",
        "quiet_from": "quiet_from", "quiet_to": "quiet_to",
        "default_model": "default_model", "creativity": "creativity",
        "retention_months": "retention_months",
    }
    data: dict = {}
    for field, col in cols.items():
        value = getattr(payload, field)
        if value is not None:
            data[col] = str(value) if "email" in col or col == "reply_to" else value
    for field, col in (("quiet_hours", "quiet_hours"), ("auto_approve", "auto_approve"), ("gdpr", "gdpr")):
        value = getattr(payload, field)
        if value is not None:
            data[col] = int(value)
    if payload.notif is not None:
        data["notif"] = db.dumps(payload.notif)

    if data:
        with db.transaction():
            db.update("workspaces", w["id"], data)
            if data.get("auto_approve"):
                log(kind="human", actor=principal.id,
                    action_en="turned on auto-approval for agent drafts",
                    action_fa="تأیید خودکار پیش‌نویس ایجنت‌ها را روشن کرد",
                    target="settings", tone="warn")
    return get_settings()


# ================================================================ billing

#: Display names for the plan ids this product ships with. Anything else is
#: shown as the id itself, which is at least true.
PLAN_NAMES = {
    "starter": {"en": "Starter", "fa": "پایه"},
    "growth": {"en": "Growth", "fa": "رشد"},
    "scale": {"en": "Scale", "fa": "اسکیل"},
}


@router.get("/billing", dependencies=[_needs("billing")])
def billing(_: Principal = Depends(requires("analytics.view"))) -> dict:
    w = _workspace()
    u = db.one("SELECT * FROM usage_counters WHERE id = 1")
    plan_id = (w["plan"] or "").strip()
    return {
        "plan": {
            "id": plan_id,
            # The plan the workspace actually records, not the literal "Scale"
            # every deployment used to be told it was on.
            "name": PLAN_NAMES.get(plan_id, {"en": plan_id.title(), "fa": plan_id.title()}),
            # Nothing in this product stores a price. Inventing 890 put a
            # number a customer could act on next to a plan name, and the
            # panel is not where this customer's billing is decided anyway.
            "price": None,
            "renews": u["renews_at"] if u else None,
        },
        "usage": {
            "emails": {"used": u["emails_used"], "limit": u["emails_limit"]} if u else {},
            "credits": {"used": u["credits_used"], "limit": u["credits_limit"]} if u else {},
            "contacts": {"used": db.scalar("SELECT COUNT(*) FROM contacts", default=0),
                         "limit": u["contacts_limit"] if u else 0},
        },
        "invoices": [ser_invoice(r) for r in db.query("SELECT * FROM invoices ORDER BY created_at DESC")],
        # No payment method is stored, because there is no processor here: in
        # this product billing is settled with the agency that sold the panel.
        # Returning a card meant every customer saw the same invented Visa.
        "method": None,
    }


# ================================================================ domains


@router.get("/domains", dependencies=[_needs("domains")])
def list_domains(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    out = []
    for row in db.query("SELECT * FROM domains ORDER BY created_at"):
        records = db.query("SELECT * FROM dns_records WHERE domain_id = ?", (row["id"],))
        out.append(ser_domain(row, records))
    return out


_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


@router.post("/domains", status_code=201, dependencies=[_needs("domains")])
def add_domain(payload: DomainIn, principal: Principal = Depends(requires("settings.write"))) -> dict:
    domain = payload.domain.strip().lower().rstrip(".")
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=422, detail="That does not look like a domain name")
    if db.one("SELECT 1 FROM domains WHERE domain = ?", (domain,)):
        raise HTTPException(status_code=409, detail="Domain already added")

    did = new_id("d")
    with db.transaction():
        db.insert("domains", {
            "id": did, "domain": domain, "status": "unverified",
            "spf": 0, "dkim": 0, "dmarc": 0, "bimi": 0,
            "ip": "dedicated-pending" if payload.dedicated else "shared",
            "dedicated": int(payload.dedicated), "reputation": 50, "created_at": iso(),
        })
        for i, (rtype, host, value) in enumerate([
            ("TXT", domain, "v=spf1 include:mailpilot.net ~all"),
            ("CNAME", f"mp1._domainkey.{domain}", "mp1.dkim.mailpilot.net"),
            ("TXT", f"_dmarc.{domain}", "v=DMARC1; p=none; rua=mailto:dmarc@" + domain),
        ]):
            db.insert("dns_records", {"id": f"{did}-r{i}", "domain_id": did, "type": rtype,
                                      "host": host, "value": value, "ok": 0})
        log(kind="human", actor=principal.id, action_en=f"added the domain {domain}",
            action_fa=f"دامنهٔ {domain} را افزود", target=did, tone="info")

    row = db.one("SELECT * FROM domains WHERE id = ?", (did,))
    return ser_domain(row, db.query("SELECT * FROM dns_records WHERE domain_id = ?", (did,)))


@router.post("/domains/{domain_id}/verify", dependencies=[_needs("domains")])
def verify_domain(domain_id: str, principal: Principal = Depends(requires("settings.write"))) -> dict:
    row = db.one("SELECT * FROM domains WHERE id = ?", (domain_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    # This used to write spf=1, dkim=1, dmarc=1 and mark every record `ok`
    # WITHOUT RESOLVING ANYTHING, so the screen a customer checks before a
    # large send showed three green ticks for a domain with no SPF record.
    # It now actually looks the records up, and anything it cannot determine
    # is recorded as unknown rather than as a pass.
    from .. import senderhealth

    found = senderhealth.refresh_auth(domain_id)
    records = db.query("SELECT * FROM dns_records WHERE domain_id = ?", (domain_id,))
    passed = all(found[k] == "pass" for k in ("spf", "dkim", "dmarc"))

    with db.transaction():
        for r in records:
            # a record's tick follows the check its type belongs to
            kind = (r["type"] or "").upper()
            host = (r["host"] or "").lower()
            if "_dmarc" in host:
                state = found["dmarc"]
            elif "_domainkey" in host:
                state = found["dkim"]
            elif kind == "TXT":
                state = found["spf"]
            else:
                state = "unknown"
            db.update("dns_records", r["id"], {"ok": 1 if state == "pass" else 0})
        if passed:
            db.update("domains", domain_id, {"reputation": max(row["reputation"], 80)})
        log(kind="system", actor="system",
            action_en=(f"verified {row['domain']}" if passed
                       else f"checked {row['domain']} — not fully authenticated"),
            action_fa=(f"دامنهٔ {row['domain']} تأیید شد" if passed
                       else f"دامنهٔ {row['domain']} بررسی شد — احراز کامل نیست"),
            target=domain_id, tone="good" if passed else "warn")

    row = db.one("SELECT * FROM domains WHERE id = ?", (domain_id,))
    return ser_domain(row, db.query("SELECT * FROM dns_records WHERE domain_id = ?", (domain_id,)))


# ================================================================ developers


@router.get("/api-keys", dependencies=[_needs("developers")])
def list_keys(_: Principal = Depends(requires("developers.manage"))) -> list[dict]:
    return [ser_key(r) for r in db.query("SELECT * FROM api_keys ORDER BY created_at DESC")]


@router.post("/api-keys", status_code=201, dependencies=[_needs("developers")])
def create_key(payload: ApiKeyIn, principal: Principal = Depends(requires("developers.manage"))) -> dict:
    plaintext, prefix, token_hash = new_api_key()
    kid = new_id("k")
    with db.transaction():
        db.insert("api_keys", {
            "id": kid, **bi_in(payload.name, "name"), "prefix": prefix,
            "token_hash": token_hash, "scopes": db.dumps(payload.scopes),
            "last_used_at": None, "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en="created an API key",
            action_fa="یک کلید API ساخت", target=kid, tone="warn")
    out = ser_key(db.one("SELECT * FROM api_keys WHERE id = ?", (kid,)))
    # The only time the plaintext ever exists in a response.
    out["token"] = plaintext
    out["warning"] = "Store this now — it cannot be shown again."
    return out


@router.delete("/api-keys/{key_id}", status_code=204, dependencies=[_needs("developers")])
def revoke_key(key_id: str, principal: Principal = Depends(requires("developers.manage"))) -> None:
    if db.one("SELECT 1 FROM api_keys WHERE id = ?", (key_id,)) is None:
        raise HTTPException(status_code=404, detail="Key not found")
    with db.transaction():
        db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        log(kind="human", actor=principal.id, action_en="revoked an API key",
            action_fa="یک کلید API را باطل کرد", target=key_id, tone="warn")


@router.get("/webhooks", dependencies=[_needs("developers")])
def list_webhooks(_: Principal = Depends(requires("developers.manage"))) -> list[dict]:
    return [ser_webhook(r) for r in db.query("SELECT * FROM webhooks ORDER BY created_at")]


WEBHOOK_EVENTS = [
    "email.delivered", "email.opened", "email.clicked", "email.bounced", "email.complained",
    "contact.created", "contact.unsubscribed", "agent.action", "agent.escalation", "experiment.called",
]


@router.get("/webhooks/events", tags=["meta"], dependencies=[_needs("developers")])
def webhook_events() -> list[str]:
    return WEBHOOK_EVENTS


@router.post("/webhooks", status_code=201, dependencies=[_needs("developers")])
def create_webhook(payload: WebhookIn, principal: Principal = Depends(requires("developers.manage"))) -> dict:
    if not payload.url.startswith("https://"):
        raise HTTPException(status_code=422, detail="Webhook endpoints must be HTTPS")
    bad = [e for e in payload.events if e not in WEBHOOK_EVENTS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown events: {', '.join(bad)}")
    wid = new_id("w")
    with db.transaction():
        db.insert("webhooks", {"id": wid, "url": payload.url, "events": db.dumps(payload.events),
                               "enabled": 1, "ok_rate": 100.0, "created_at": iso()})
    return ser_webhook(db.one("SELECT * FROM webhooks WHERE id = ?", (wid,)))


@router.patch("/webhooks/{webhook_id}", dependencies=[_needs("developers")])
def update_webhook(
    webhook_id: str, payload: WebhookPatch, _: Principal = Depends(requires("developers.manage"))
) -> dict:
    if db.one("SELECT 1 FROM webhooks WHERE id = ?", (webhook_id,)) is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    data: dict = {}
    if payload.url is not None:
        if not payload.url.startswith("https://"):
            raise HTTPException(status_code=422, detail="Webhook endpoints must be HTTPS")
        data["url"] = payload.url
    if payload.events is not None:
        bad = [e for e in payload.events if e not in WEBHOOK_EVENTS]
        if bad:
            raise HTTPException(status_code=422, detail=f"Unknown events: {', '.join(bad)}")
        data["events"] = db.dumps(payload.events)
    if payload.on is not None:
        data["enabled"] = int(payload.on)
    if data:
        with db.transaction():
            db.update("webhooks", webhook_id, data)
    return ser_webhook(db.one("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)))


@router.delete("/webhooks/{webhook_id}", status_code=204, dependencies=[_needs("developers")])
def delete_webhook(webhook_id: str, _: Principal = Depends(requires("developers.manage"))) -> None:
    if db.one("SELECT 1 FROM webhooks WHERE id = ?", (webhook_id,)) is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    with db.transaction():
        db.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))


# ================================================================ integrations


@router.get("/integrations", dependencies=[_needs("integrations")])
def list_integrations(_: Principal = Depends(current_principal)) -> list[dict]:
    return [ser_integration(r) for r in db.query("SELECT * FROM integrations ORDER BY category, name")]


@router.patch("/integrations/{integration_id}", dependencies=[_needs("integrations")])
def toggle_integration(
    integration_id: str, payload: IntegrationPatch, principal: Principal = Depends(requires("settings.write"))
) -> dict:
    if db.one("SELECT 1 FROM integrations WHERE id = ?", (integration_id,)) is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    with db.transaction():
        db.update("integrations", integration_id, {"enabled": int(payload.on)})
        log(kind="human", actor=principal.id,
            action_en=f"{'connected' if payload.on else 'disconnected'} {integration_id}",
            action_fa=f"{integration_id} را {'متصل' if payload.on else 'قطع'} کرد",
            target=integration_id, tone="info")
    return ser_integration(db.one("SELECT * FROM integrations WHERE id = ?", (integration_id,)))


# ================================================================ templates


@router.get("/templates")
def list_templates(category: str = "all", _: Principal = Depends(current_principal)) -> list[dict]:
    if category == "all":
        rows = db.query("SELECT * FROM templates ORDER BY used DESC")
    else:
        rows = db.query("SELECT * FROM templates WHERE category = ? ORDER BY used DESC", (category,))
    return [ser_template(r) for r in rows]


@router.post("/templates", status_code=201)
def create_template(payload: TemplateIn, _: Principal = Depends(requires("content.edit"))) -> dict:
    tid = new_id("tp")
    with db.transaction():
        db.insert("templates", {
            "id": tid, **bi_in(payload.name, "name"),
            "category": payload.category, "used": 0,
            "accent": payload.accent, "created_at": iso(), "updated_at": iso(),
            # sanitised here too: this is a second way HTML enters the system
            "html": sanitize(payload.html) if payload.html else "",
            "subject_en": payload.subject, "subject_fa": payload.subject,
            "source": payload.source,
        })
    return ser_template(db.one("SELECT * FROM templates WHERE id = ?", (tid,)))


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str, _: Principal = Depends(requires("content.edit"))) -> None:
    if db.one("SELECT 1 FROM templates WHERE id = ?", (template_id,)) is None:
        raise HTTPException(status_code=404, detail="Template not found")
    with db.transaction():
        db.execute("DELETE FROM templates WHERE id = ?", (template_id,))


# ================================================================ brand brain


@router.get("/knowledge")
def knowledge(_: Principal = Depends(current_principal)) -> dict:
    voice = db.one("SELECT * FROM brand_voice WHERE id = 1")
    sources = db.query("SELECT * FROM kb_sources ORDER BY created_at DESC")
    return {
        "voice": {
            "axes": db.loads(voice["axes"]) if voice else [],
            "banned": db.loads(voice["banned"]) if voice else [],
            "notes": voice["notes"] if voice else "",
        },
        "sources": [ser_kb(r) for r in sources],
        "chunks": sum(r["chunks"] for r in sources),
    }


@router.patch("/knowledge/voice")
def update_voice(payload: BrandVoiceIn, principal: Principal = Depends(requires("content.edit"))) -> dict:
    data: dict = {}
    if payload.axes is not None:
        data["axes"] = db.dumps(payload.axes)
    if payload.banned is not None:
        data["banned"] = db.dumps([b.strip() for b in payload.banned if b.strip()])
    if payload.notes is not None:
        data["notes"] = payload.notes
    if data:
        with db.transaction():
            if db.one("SELECT 1 FROM brand_voice WHERE id = 1") is None:
                db.insert("brand_voice", {"id": 1, "axes": "[]", "banned": "[]", "notes": ""})
            db.update("brand_voice", 1, data)
    return knowledge()


@router.post("/knowledge/sources", status_code=201)
def add_source(payload: KbSourceIn, _: Principal = Depends(requires("content.edit"))) -> dict:
    kid = new_id("kb")
    with db.transaction():
        db.insert("kb_sources", {"id": kid, **bi_in(payload.name, "name"), "type": payload.type,
                                 "chunks": 0, "status": "indexing", "created_at": iso()})
    return ser_kb(db.one("SELECT * FROM kb_sources WHERE id = ?", (kid,)))


@router.delete("/knowledge/sources/{source_id}", status_code=204)
def delete_source(source_id: str, _: Principal = Depends(requires("content.edit"))) -> None:
    if db.one("SELECT 1 FROM kb_sources WHERE id = ?", (source_id,)) is None:
        raise HTTPException(status_code=404, detail="Source not found")
    with db.transaction():
        db.execute("DELETE FROM kb_sources WHERE id = ?", (source_id,))


# ================================================================ activity


@router.get("/activity")
def list_activity(
    kind: str = "all",
    q: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: Principal = Depends(current_principal),
) -> dict:
    where = ["1=1"]
    params: list = []
    if kind != "all":
        where.append("kind = ?")
        params.append(kind)
    if q:
        where.append("(action_en LIKE ? ESCAPE '\\' OR action_fa LIKE ? ESCAPE '\\' "
                     "OR target LIKE ? ESCAPE '\\' OR actor LIKE ? ESCAPE '\\')")
        params += [like(q)] * 4
    rows = db.query(f"SELECT * FROM activity WHERE {' AND '.join(where)} ORDER BY created_at DESC", params)
    out = paginate(rows, page, size)
    out["items"] = [ser_activity(r) for r in out["items"]]
    return out


# ================================================================ notifications


@router.get("/notifications")
def list_notifications(_: Principal = Depends(current_principal)) -> dict:
    rows = db.query("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 50")
    return {"items": [ser_notif(r) for r in rows],
            "unread": db.scalar("SELECT COUNT(*) FROM notifications WHERE unread = 1", default=0)}


@router.post("/notifications/read", status_code=204)
def mark_all_read(_: Principal = Depends(current_user)) -> None:
    with db.transaction():
        db.execute("UPDATE notifications SET unread = 0")


@router.post("/notifications/{notification_id}/read", status_code=204)
def mark_read(notification_id: str, _: Principal = Depends(current_user)) -> None:
    if db.one("SELECT 1 FROM notifications WHERE id = ?", (notification_id,)) is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    with db.transaction():
        db.update("notifications", notification_id, {"unread": 0})
