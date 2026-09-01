"""Shared domain logic: bilingual serialisation, roles, metrics.

The single most important thing in this module is `bi()`.

The frontend renders every human-readable name through `loc(value, lang)`,
which expects `{ "en": "...", "fa": "..." }`. Campaign names, agent roles and
contact names are CONTENT, not interface strings — they do not belong in the
i18n dictionaries, and the API must not pick a language on the client's behalf.
So the API always returns both, and the client chooses. That one decision is
what lets the language switch stay instant and client-side.
"""

from __future__ import annotations

import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from . import db


# ---------------------------------------------------------------- time


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ago_iso(**kwargs: float) -> str:
    return iso(utcnow() - timedelta(**kwargs))


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- bilingual


def bi(row: Any, base: str) -> dict[str, str]:
    """`bi(row, "name")` -> `{"en": row["name_en"], "fa": row["name_fa"]}`.

    Falls back to English when a translation is missing, which is the same
    rule the client's `loc()` uses — so a half-translated record degrades the
    same way on both sides instead of rendering an empty string.
    """
    en = (row[f"{base}_en"] if f"{base}_en" in row.keys() else "") or ""
    fa = (row[f"{base}_fa"] if f"{base}_fa" in row.keys() else "") or ""
    return {"en": en, "fa": fa or en}


#: Every human-readable name in this schema is a table cell, a subject line or
#: a log row. A 50,000-character campaign name was accepted before this and
#: broke every list it appeared in.
MAX_NAME = 200


def bi_get(payload: dict[str, Any] | str | None, lang: str = "en", default: str = "") -> str:
    """One side of a bilingual field, whichever shape it arrived in.

    `Lang` is `dict[str, str] | str`, so `payload.en` is an AttributeError
    waiting for the first client that sends the dict form — which is all of
    them. Anything that needs one language reads it through here.
    """
    if payload is None:
        return default
    if isinstance(payload, str):
        return payload
    return str(payload.get(lang) or payload.get("en") or payload.get("fa") or default)


def bi_in(payload: dict[str, Any] | None, base: str, default: str = "") -> dict[str, str]:
    """The inverse, for writes: accepts either a plain string or {en, fa}.

    Every bilingual write in the product passes through here, which makes it
    the one place a length limit can be applied without being forgotten on the
    next endpoint someone adds.
    """
    if payload is None:
        return {f"{base}_en": default, f"{base}_fa": default}
    if isinstance(payload, str):
        return {f"{base}_en": payload[:MAX_NAME], f"{base}_fa": payload[:MAX_NAME]}
    en = str(payload.get("en") or payload.get("fa") or default)[:MAX_NAME]
    fa = str(payload.get("fa") or en)[:MAX_NAME]
    return {f"{base}_en": en, f"{base}_fa": fa}


# ---------------------------------------------------------------- roles

ROLES = ("owner", "admin", "editor", "analyst", "viewer")

# Mirrors the permission matrix printed on the Team page. Kept as data so the
# UI and the API can never disagree about what a role means — the matrix is
# served from `/meta/permissions`.
PERMISSIONS: dict[str, tuple[str, ...]] = {
    "campaigns.send": ("owner", "admin", "editor"),
    "campaigns.write": ("owner", "admin", "editor"),
    "agents.deploy": ("owner", "admin"),
    "contacts.read": ("owner", "admin", "editor", "analyst", "viewer"),
    "contacts.write": ("owner", "admin", "editor"),
    "contacts.export": ("owner", "admin"),
    "content.edit": ("owner", "admin", "editor"),
    "analytics.view": ("owner", "admin", "editor", "analyst", "viewer"),
    "billing.manage": ("owner",),
    "team.invite": ("owner", "admin"),
    "settings.write": ("owner", "admin"),
    "developers.manage": ("owner", "admin"),
}


def can(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, ())


# ---------------------------------------------------------------- series


def seeded_series(
    n: int,
    *,
    base: float = 100,
    trend: float = 0.4,
    noise: float = 0.12,
    weekly: float = 0.18,
    seed: int = 7,
    spike_at: int | None = None,
) -> list[int]:
    """Deterministic pseudo-data with weekly seasonality.

    Same shape as the frontend's generator so a chart looks identical whether
    it is being served from here or from the mock — which is what makes
    swapping one for the other a one-line change in the client.
    """
    rng = random.Random(seed)
    out: list[int] = []
    for i in range(n):
        t = base * (1 + (trend * i) / max(n, 1))
        s = 1 + weekly * math.sin((i / 7) * math.pi * 2)
        e = 1 + (rng.random() - 0.5) * noise * 2
        spike = 1.7 if spike_at == i else 1.0
        out.append(max(0, round(t * s * e * spike)))
    return out


def day_keys(n: int) -> list[str]:
    """The last `n` days as ISO dates — the client formats them for display."""
    today = utcnow().date()
    return [(today - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]


# ---------------------------------------------------------------- metrics


def _rate(part: float, whole: float) -> float:
    return round((part / whole) * 100, 4) if whole else 0.0


def totals(range_days: int | None = None) -> dict[str, Any]:
    """Programme-wide figures, computed from the campaigns that actually sent."""
    where = "WHERE sent > 0"
    params: list[Any] = []
    if range_days:
        where += " AND updated_at >= ?"
        params.append(ago_iso(days=range_days))

    row = db.one(
        f"""
        SELECT COALESCE(SUM(sent),0) sent, COALESCE(SUM(delivered),0) delivered,
               COALESCE(SUM(opens),0) opens, COALESCE(SUM(clicks),0) clicks,
               COALESCE(SUM(replies),0) replies, COALESCE(SUM(bounces),0) bounces,
               COALESCE(SUM(unsubs),0) unsubs, COALESCE(SUM(revenue),0) revenue
        FROM campaigns {where}
        """,
        params,
    )
    sent = row["sent"] or 0
    contacts = db.scalar("SELECT COUNT(*) FROM contacts", default=0)
    return {
        "sent": sent,
        "delivered": row["delivered"],
        "opens": row["opens"],
        "clicks": row["clicks"],
        "replies": row["replies"],
        "bounces": row["bounces"],
        "unsubs": row["unsubs"],
        "revenue": round(row["revenue"], 2),
        "openRate": _rate(row["opens"], sent),
        "clickRate": _rate(row["clicks"], sent),
        "replyRate": _rate(row["replies"], sent),
        "bounceRate": _rate(row["bounces"], sent),
        "unsubRate": _rate(row["unsubs"], sent),
        "deliveryRate": _rate(row["delivered"], sent),
        "contacts": contacts,
    }


def send_heatmap() -> list[list[float]]:
    """Open rate by weekday x 2-hour bucket.

    Modelled rather than sampled: a morning peak, a smaller evening one, and a
    flatter weekend. Real data would replace the model, and the shape the
    client draws would not change.
    """
    rng = random.Random(1234)
    grid: list[list[float]] = []
    for d in range(7):
        row: list[float] = []
        for h in range(12):
            hour = h * 2
            morning = math.exp(-((hour - 9) ** 2) / 12) * 1.0
            evening = math.exp(-((hour - 20) ** 2) / 18) * 0.55
            weekend = 0.62 if d >= 5 else 1.0
            row.append(round((morning + evening) * weekend * (0.85 + rng.random() * 0.3) * 62, 1))
        grid.append(row)
    return grid


def cohorts(months: int = 6) -> list[dict[str, Any]]:
    rng = random.Random(555)
    now = utcnow()
    out = []
    for i in range(months):
        month = (now - timedelta(days=30 * (months - 1 - i))).strftime("%Y-%m")
        values = [
            round(100 * math.exp(-p * 0.28) * (0.85 + rng.random() * 0.25)) if p <= months - 1 - i else 0
            for p in range(months)
        ]
        out.append({"month": month, "values": values})
    return out


# ---------------------------------------------------------------- activity


def log(
    *,
    kind: str,
    actor: str,
    action_en: str,
    action_fa: str,
    target: str = "",
    tone: str = "info",
    ip: str = "",
) -> None:
    from .security import new_id

    db.insert(
        "activity",
        {
            "id": new_id("a"),
            "kind": kind,
            "actor": actor,
            "action_en": action_en,
            "action_fa": action_fa,
            "target": target,
            "tone": tone,
            "ip": ip,
            "created_at": iso(),
        },
    )


def record_event(event_type: str, email: str = "", campaign_id: str | None = None) -> None:
    from .security import new_id

    db.insert(
        "events",
        {
            "id": new_id("e"),
            "type": event_type,
            "email": email,
            "campaign_id": campaign_id,
            "created_at": iso(),
        },
    )


# ---------------------------------------------------------------- paging


def paginate(rows: Sequence[Any], page: int, size: int) -> dict[str, Any]:
    total = len(rows)
    pages = max(1, math.ceil(total / size)) if size else 1
    page = max(1, min(page, pages))
    start = (page - 1) * size
    return {"items": list(rows[start : start + size]), "page": page, "pages": pages, "total": total, "size": size}


def like(value: str) -> str:
    """Escape the wildcards so a search for "100%" does not match everything."""
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
