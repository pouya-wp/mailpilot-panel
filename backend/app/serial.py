"""Row -> JSON.

Every shape here matches what the React app already consumes, field for field,
so pointing the client at the API is a change of data source and not a rewrite.
Where the mock had a nested object (`name: {en, fa}`), so does this.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from . import db
from .domain import bi


def _rate(part: float, whole: float) -> float:
    return round((part / whole) * 100, 4) if whole else 0.0


def agent(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "role": bi(row, "role"),
        "emoji": row["emoji"],
        "tint": row["tint"],
        "model": row["model"],
        "autonomy": row["autonomy"],
        "status": row["status"],
        "runs": row["runs"],
        "success": row["success"],
        "actionsToday": row["actions_today"],
        "budget": row["budget"],
        "temperature": row["temperature"],
        "lastRun": row["last_run_at"],
        "skills": db.loads(row["skills"]),
        "tools": db.loads(row["tools"]),
        "instructions": row["instructions"],
        "memory": db.loads(row["memory"]),
        "sparkline": db.loads(row["sparkline"]),
    }


def segment(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "emoji": row["emoji"],
        "tint": row["tint"],
        "size": _segment_size(row),
        "growth": row["growth"],
        "openRate": row["open_rate"],
        "live": bool(row["live"]),
        "match": row["match_mode"],
        "rules": db.loads(row["rules"]),
    }


def _segment_size(row: sqlite3.Row) -> int:
    """How many people are in this group RIGHT NOW.

    `segments.size` is a column, written when the group was created or edited
    and never touched again. A segment is a rule, though — tag three more
    people and the group really does contain three more — so the stored number
    started lying the moment anything changed. The list said "VIPs · 2" while
    the group held 3, and the campaign screen repeated that number next to a
    send button, which made it a promise about who was about to be mailed.

    Counted live instead. There are at most a dozen groups on a screen and the
    query is indexed; being right is worth one COUNT each.
    """
    from .routers.audience import UnknownField, _compile_rules

    try:
        where, params = _compile_rules(db.loads(row["rules"]), row["match_mode"])
    except (UnknownField, ValueError):
        # a rule saved before the field was validated; the preview reports the
        # same zero and says why, rather than quietly widening to everyone
        return 0
    return db.scalar(
        f"SELECT COUNT(*) FROM contacts WHERE {where} AND status = 'subscribed'",
        params, default=0,
    ) or 0


def campaign(row: sqlite3.Row, *, detail: bool = False) -> dict[str, Any]:
    sent = row["sent"] or 0
    out = {
        "id": row["id"],
        "name": bi(row, "name"),
        "subject": bi(row, "subject"),
        "type": row["type"],
        # How it was written, so the panel can show the right progress: a
        # professional campaign researches and writes before it sends, and
        # "queued" means something different in each mode.
        "writeMode": _maybe(row, "write_mode") or "manual",
        "goal": _maybe(row, "goal") or "",
        "status": row["status"],
        "agent": row["agent_id"],
        "segment": row["segment_id"],
        "recipients": row["recipients"],
        "sent": sent,
        "delivered": row["delivered"],
        "opens": row["opens"],
        "clicks": row["clicks"],
        "replies": row["replies"],
        "unsubs": row["unsubs"],
        "bounces": row["bounces"],
        "revenue": row["revenue"],
        "scheduledFor": row["scheduled_for"],
        "updated": row["updated_at"],
        "created": row["created_at"],
        "trend": db.loads(row["trend"]),
        # derived, so the client never divides by zero itself
        "openRate": _rate(row["opens"], sent),
        "clickRate": _rate(row["clicks"], sent),
        "deliveryRate": _rate(row["delivered"], sent),
    }
    if detail:
        out["body"] = bi(row, "body")
    return out


def contact(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "email": row["email"],
        "status": row["status"],
        "score": row["score"],
        "ltv": row["ltv"],
        "orders": row["orders"],
        "tags": db.loads(row["tags"]),
        "source": {"id": row["source_id"], **bi(row, "source")},
        "country": row["country"],
        "device": row["device"],
        "lastOpen": row["last_open_at"],
        "created": row["created_at"],
    }


def template(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "category": row["category"],
        "used": row["used"],
        "accent": row["accent"],
        # `hasHtml` rather than the HTML itself: a template list of twenty
        # documents would be a megabyte, and the list only needs to know
        # whether there is anything to preview.
        "hasHtml": bool(_maybe(row, "html")),
        "isDefault": bool(_maybe(row, "is_default")),
        "subject": _maybe(row, "subject_en") or "",
        "source": _maybe(row, "source") or "manual",
    }


def _maybe(row: sqlite3.Row, key: str) -> Any:
    """Read a column that older databases may not have yet."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def journey(row: sqlite3.Row, steps: list[sqlite3.Row] | None = None) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "name": bi(row, "name"),
        "trigger": bi(row, "trigger"),
        "status": row["status"],
        "enrolled": row["enrolled"],
        "completed": row["completed"],
        "conversion": row["conversion"],
        "agent": row["agent_id"],
    }
    if steps is not None:
        out["steps"] = [
            {"id": s["id"], "type": s["type"], "label": bi(s, "label")} for s in steps
        ]
    return out


def thread(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "from": bi(row, "from"),
        "email": row["email"],
        "subject": bi(row, "subject"),
        "preview": bi(row, "preview"),
        "draft": bi(row, "draft"),
        "intent": row["intent"],
        "sentiment": row["sentiment"],
        "handled": bool(row["handled"]),
        "agent": row["agent_id"],
        "assignee": row["assignee_id"],
        "at": row["received_at"],
    }


def experiment(row: sqlite3.Row, variants: list[sqlite3.Row]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "status": row["status"],
        "metric": row["metric"],
        "confidence": row["confidence"],
        "autoPromote": bool(row["auto_promote"]),
        "variants": [
            {
                "id": v["id"],
                "label": v["label"],
                "text": bi(v, "text"),
                "split": v["split"],
                "sent": v["sent"],
                "rate": v["rate"],
                "winner": bool(v["winner"]),
            }
            for v in variants
        ],
    }


def suppression(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "email": row["email"], "reason": row["reason"], "at": row["created_at"]}


def domain_row(row: sqlite3.Row, records: list[sqlite3.Row]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "domain": row["domain"],
        "status": row["status"],
        "spf": bool(row["spf"]),
        "dkim": bool(row["dkim"]),
        "dmarc": bool(row["dmarc"]),
        "bimi": bool(row["bimi"]),
        "ip": row["ip"],
        "dedicated": bool(row["dedicated"]),
        "reputation": row["reputation"],
        "records": [
            {"id": r["id"], "type": r["type"], "host": r["host"], "value": r["value"], "ok": bool(r["ok"])}
            for r in records
        ],
    }


def integration(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "cat": row["category"],
        "on": bool(row["enabled"]),
        "emoji": row["emoji"],
        "desc": bi(row, "desc"),
    }


def kb_source(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "type": row["type"],
        "chunks": row["chunks"],
        "status": row["status"],
        "at": row["created_at"],
    }


def user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "email": row["email"],
        "role": row["role"],
        "status": row["status"],
        "active": row["last_active_at"],
    }


def api_key(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": bi(row, "name"),
        "prefix": row["prefix"],
        "scopes": db.loads(row["scopes"]),
        "lastUsed": row["last_used_at"],
        "created": row["created_at"],
    }


def webhook(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "url": row["url"],
        "events": db.loads(row["events"]),
        "on": bool(row["enabled"]),
        "ok": row["ok_rate"],
    }


def activity(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "actor": row["actor"],
        "action": bi(row, "action"),
        "target": row["target"],
        "tone": row["tone"],
        "ip": row["ip"],
        "at": row["created_at"],
    }


def notification(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tone": row["tone"],
        "title": bi(row, "title"),
        "body": bi(row, "body"),
        "unread": bool(row["unread"]),
        "at": row["created_at"],
    }


def recommendation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "agent": row["agent_id"],
        "lift": row["lift"],
        "effort": row["effort"],
        "title": bi(row, "title"),
        "body": bi(row, "body"),
        "state": row["state"],
    }


def event(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "type": row["type"], "who": row["email"], "at": row["created_at"]}


def invoice(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "amount": row["amount"], "status": row["status"], "date": row["created_at"]}
