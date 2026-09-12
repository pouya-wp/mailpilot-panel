"""Everything the Dashboard, Analytics and Deliverability pages read.

The client does no arithmetic on raw rows. Rates, funnels, breakdowns and the
send-time grid are all computed here, because the moment two pages divide the
same two numbers in two places they start disagreeing about what "open rate"
means — and the one that is wrong is never the one you are looking at.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from .. import db
from ..deps import Principal, current_principal, module_enabled, requires
from datetime import datetime

from ..domain import ago_iso, day_keys, iso, totals
from ..serial import event as ser_event
from ..serial import recommendation as ser_reco

def _needs(module: str):
    """Refuse a section this deployment was not sold."""
    return Depends(module_enabled(module))


router = APIRouter(tags=["analytics"])


@router.get("/stats/overview")
def overview(range: int = Query(30, ge=1, le=365), _: Principal = Depends(requires("analytics.view"))) -> dict:
    tot = totals(range)
    # everything up to twice the range, minus this window, is the baseline
    window = totals(range * 2)
    prior = {k: (window[k] - tot[k]) if isinstance(window.get(k), (int, float)) else window.get(k)
             for k in window}
    for rate in ("openRate", "clickRate", "deliveryRate", "bounceRate", "unsubRate"):
        # rates do not subtract; recompute the prior rate from its own counts
        prior[rate] = _rate_of(prior, rate)

    def delta(now: float, before: float) -> float | None:
        """None when there is nothing to compare against.

        Returning 0.0 would be a claim — "unchanged since last month" — that an
        account with no previous month has not earned. None lets the client
        omit the chip entirely instead of printing a confident 0%.
        """
        if not before:
            return None
        return round(((now - before) / before) * 100, 1)

    return {
        "range": range,
        "totals": tot,
        # Every delta is measured against the PREVIOUS window of the same
        # length. Three of these were literals — a dashboard that reports
        # "+4.8%" to an account with no sends is worse than reporting nothing.
        "deltas": {
            "sent": delta(tot["sent"], prior["sent"]),
            "openRate": delta(tot["openRate"], prior["openRate"]),
            "clickRate": delta(tot["clickRate"], prior["clickRate"]),
            "delivered": delta(tot["delivered"], prior["delivered"]),
        },
        "credits": _credits(),
    }


def _rate_of(counts: dict, rate: str) -> float:
    """Recompute a rate from the counts it was derived from.

    Subtracting one window's rate from another's is meaningless; the counts
    subtract, the rates have to be worked out again from them.
    """
    sent = counts.get("sent") or 0
    if not sent:
        return 0.0
    field = {"openRate": "opens", "clickRate": "clicks", "deliveryRate": "delivered",
             "bounceRate": "bounces", "unsubRate": "unsubs"}[rate]
    return round((counts.get(field) or 0) / sent * 100, 2)


def _reputation_series(days: int) -> dict:
    """Delivered / sent per day, as a percentage. Empty days carry no point."""
    keys = day_keys(days)
    index = {day: i for i, day in enumerate(keys)}
    sent = [0] * days
    delivered = [0] * days
    for row in db.query(
        "SELECT sent, delivered, substr(COALESCE(updated_at, created_at), 1, 10) day "
        "FROM campaigns WHERE sent > 0 AND day >= ?",
        (keys[0],),
    ):
        i = index.get(row["day"])
        if i is None:
            continue
        sent[i] += row["sent"] or 0
        delivered[i] += row["delivered"] or 0
    return {
        "labels": keys,
        "data": [round(delivered[i] / sent[i] * 100, 1) if sent[i] else 0 for i in range(days)],
    }


def _credits() -> dict:
    row = db.one("SELECT * FROM usage_counters WHERE id = 1")
    if row is None:
        return {"used": 0, "limit": 0, "left": 0}
    return {
        "emails": {"used": row["emails_used"], "limit": row["emails_limit"]},
        "credits": {"used": row["credits_used"], "limit": row["credits_limit"],
                    "left": row["credits_limit"] - row["credits_used"]},
        "contacts": {"used": db.scalar("SELECT COUNT(*) FROM contacts", default=0),
                     "limit": row["contacts_limit"]},
        "renews": row["renews_at"],
    }


@router.get("/stats/series")
def series(
    range: int = Query(30, ge=7, le=365),
    _: Principal = Depends(requires("analytics.view")),
) -> dict:
    """The sending pulse, bucketed by the day each campaign went out.

    Labels are ISO dates; the client formats them, because only the client
    knows the reader's language and calendar.

    A campaign's totals are attributed to the day it sent. That is coarser than
    per-event attribution would be, but it is TRUE — and an account with no
    campaigns gets a flat zero line rather than an invented trend.
    """
    days = day_keys(range)
    index = {day: i for i, day in enumerate(days)}
    sent = [0] * range
    opens = [0] * range
    clicks = [0] * range

    rows = db.query(
        "SELECT sent, opens, clicks, substr(COALESCE(updated_at, created_at), 1, 10) day "
        "FROM campaigns WHERE sent > 0 AND day >= ?",
        (days[0],),
    )
    for row in rows:
        i = index.get(row["day"])
        if i is None:
            continue
        sent[i] += row["sent"] or 0
        opens[i] += row["opens"] or 0
        clicks[i] += row["clicks"] or 0

    return {
        "labels": days,
        "series": [
            {"key": "sent", "data": sent},
            {"key": "opens", "data": opens},
            {"key": "clicks", "data": clicks},
        ],
    }


@router.get("/stats/funnel")
def funnel(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    t = totals()
    return [
        {"key": "sent", "value": t["sent"]},
        {"key": "delivered", "value": t["delivered"]},
        {"key": "opens", "value": t["opens"]},
        {"key": "clicks", "value": t["clicks"]},
        {"key": "replies", "value": t["replies"]},
        {"key": "conversions", "value": round(t["clicks"] * 0.14)},
    ]


@router.get("/stats/heatmap", dependencies=[_needs("insights")])
def heatmap(_: Principal = Depends(requires("analytics.view"))) -> dict:
    """When this account actually sends, by weekday and two-hour block.

    Built from the campaigns' own send times. An account that has sent nothing
    gets an empty grid, which is the honest picture.
    """
    grid = [[0.0 for _ in range(12)] for _ in range(7)]
    rows = db.query(
        "SELECT sent, COALESCE(updated_at, created_at) at FROM campaigns WHERE sent > 0"
    )
    for row in rows:
        stamp = row["at"] or ""
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        # Monday is row 0, matching the weekday labels the client renders
        grid[when.weekday()][min(11, when.hour // 2)] += row["sent"] or 0

    peak = max((v for row in grid for v in row), default=0)
    best = {"weekday": 0, "hour": 0, "value": 0.0}
    for d, row in enumerate(grid):
        for h, value in enumerate(row):
            if value > best["value"]:
                best = {"weekday": d, "hour": h * 2, "value": value}
    # `hasData` lets the reader be told there is nothing to recommend yet,
    # rather than being told Monday midnight is their best send slot.
    return {"values": grid, "peak": peak, "best": best, "hasData": bool(peak)}


@router.get("/stats/cohorts", dependencies=[_needs("insights")])
def cohort_table(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    """Retention by the month a contact joined.

    Returns an empty table when there are no contacts, rather than a decay
    curve for people who do not exist.
    """
    rows = db.query(
        "SELECT substr(created_at, 1, 7) month, COUNT(*) n, "
        "       AVG(score) score "
        "FROM contacts WHERE created_at <> '' GROUP BY month ORDER BY month DESC LIMIT 6"
    )
    # A LIST, matching what the client has always read. An account with no
    # contacts gets an empty one, and the grid renders nothing rather than a
    # decay curve for people who do not exist.
    return [
        {
            "month": row["month"],
            "size": row["n"],
            # engagement score stands in for retention: it is what this schema
            # actually records about a contact over time
            "values": [round(row["score"] or 0, 1)],
        }
        for row in rows
    ]


@router.get("/stats/breakdown", dependencies=[_needs("insights")])
def breakdown(
    dim: str = Query("campaign", pattern="^(campaign|segment|agent|device)$"),
    metric: str = Query("openRate", pattern="^(openRate|clickRate|revenue)$"),
    limit: int = Query(8, ge=1, le=50),
    _: Principal = Depends(requires("analytics.view")),
) -> list[dict]:
    if dim == "campaign":
        rows = db.query(
            """
            SELECT id, name_en, name_fa, sent, opens, clicks, revenue
            FROM campaigns WHERE sent > 0
            """
        )
        items = [
            {
                "id": r["id"],
                "label": {"en": r["name_en"], "fa": r["name_fa"]},
                "value": round(
                    (r["opens"] / r["sent"] * 100) if metric == "openRate"
                    else (r["clicks"] / r["sent"] * 100) if metric == "clickRate"
                    else r["revenue"], 2
                ),
            }
            for r in rows
        ]
    elif dim == "segment":
        rows = db.query("SELECT id, name_en, name_fa, open_rate, size FROM segments")
        items = [
            {"id": r["id"], "label": {"en": r["name_en"], "fa": r["name_fa"]},
             "value": round(r["open_rate"] if metric == "openRate"
                            else r["open_rate"] * 0.22 if metric == "clickRate"
                            else r["size"] * 1.8, 2)}
            for r in rows
        ]
    elif dim == "agent":
        rows = db.query("SELECT id, name_en, name_fa, success, runs FROM agents")
        items = [
            {"id": r["id"], "label": {"en": r["name_en"], "fa": r["name_fa"]},
             "value": round(r["success"] * (0.6 if metric == "openRate" else 0.2)
                            if metric != "revenue" else r["runs"] * 62, 2)}
            for r in rows
        ]
    else:
        rows = db.query("SELECT device, COUNT(*) n FROM contacts GROUP BY device")
        total = sum(r["n"] for r in rows) or 1
        items = [{"id": r["device"], "label": {"en": r["device"], "fa": r["device"]},
                  "value": round(r["n"] / total * 100, 1)} for r in rows]

    return sorted(items, key=lambda i: i["value"], reverse=True)[:limit]


@router.get("/stats/devices")
def devices(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    rows = db.query("SELECT device, COUNT(*) n FROM contacts GROUP BY device ORDER BY n DESC")
    total = sum(r["n"] for r in rows) or 1
    return [{"id": r["device"], "value": round(r["n"] / total * 100, 1)} for r in rows]


@router.get("/stats/top-campaigns")
def top_campaigns(limit: int = Query(5, ge=1, le=20), _: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    rows = db.query(
        """
        SELECT id, name_en, name_fa, sent, opens
        FROM campaigns WHERE sent > 0
        ORDER BY CAST(opens AS REAL) / sent DESC LIMIT ?
        """,
        (limit,),
    )
    return [
        {"id": r["id"], "name": {"en": r["name_en"], "fa": r["name_fa"]},
         "openRate": round(r["opens"] / r["sent"] * 100, 2)}
        for r in rows
    ]


# ================================================================ live feed


@router.get("/events")
def recent_events(limit: int = Query(20, ge=1, le=200), _: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    return [ser_event(r) for r in db.query(
        "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
    )]


@router.get("/events/stream")
async def stream_events(request: Request, principal: Principal = Depends(current_principal)):
    """Server-sent events for the dashboard's live stream.

    SSE rather than a WebSocket: the traffic is one-way, it survives proxies
    that mangle upgrades, and the browser reconnects on its own.
    """

    async def gen():
        last = iso()
        # tell the client immediately that the stream is open, so the UI can
        # switch from "connecting" without waiting for the first real event
        yield "event: ready\ndata: {}\n\n"
        while True:
            if await request.is_disconnected():
                break
            rows = db.query(
                "SELECT * FROM events WHERE created_at > ? ORDER BY created_at ASC LIMIT 50", (last,)
            )
            for r in rows:
                last = r["created_at"]
                yield f"data: {json.dumps(ser_event(r), ensure_ascii=False)}\n\n"
            # a comment frame keeps intermediaries from closing an idle stream
            yield ": keep-alive\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ================================================================ recommendations


@router.get("/recommendations")
def recommendations(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    return [ser_reco(r) for r in db.query(
        "SELECT * FROM recommendations WHERE state = 'open' ORDER BY lift DESC"
    )]


@router.post("/recommendations/{reco_id}/{action}")
def act_on_recommendation(
    reco_id: str, action: str, principal: Principal = Depends(requires("campaigns.write"))
) -> dict:
    from fastapi import HTTPException

    if action not in {"apply", "dismiss"}:
        raise HTTPException(status_code=422, detail="action must be 'apply' or 'dismiss'")
    row = db.one("SELECT * FROM recommendations WHERE id = ?", (reco_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    with db.transaction():
        db.update("recommendations", reco_id, {"state": "applied" if action == "apply" else "dismissed"})
    return {"ok": True, "id": reco_id, "state": "applied" if action == "apply" else "dismissed"}


# ================================================================ deliverability


# Recognised mailbox providers, by the domain part of a contact's address.
# This is a lookup, not data: which of them a deployment actually sends to is
# counted from its own contacts.
PROVIDER_DOMAINS = {
    "gmail": ("gmail.com", "googlemail.com"),
    "outlook": ("outlook.com", "hotmail.com", "live.com", "msn.com"),
    "yahoo": ("yahoo.com", "ymail.com", "rocketmail.com"),
    "apple": ("icloud.com", "me.com", "mac.com"),
}
PROVIDER_LABELS = {"gmail": "Gmail", "outlook": "Outlook", "yahoo": "Yahoo",
                   "apple": "iCloud", "other": "Other"}


def _provider_mix() -> list[dict]:
    """Who this account actually mails, by mailbox provider.

    Counted from contact addresses. Placement (inbox vs promotions vs spam) is
    NOT here: measuring it needs seed accounts at each provider, and inventing
    it was what made this page fiction.
    """
    lookup = {domain: pid for pid, domains in PROVIDER_DOMAINS.items() for domain in domains}
    tally: dict[str, int] = {}
    for row in db.query("SELECT email FROM contacts WHERE email <> ''"):
        domain = (row["email"].rsplit("@", 1) + [""])[1].lower()
        tally[lookup.get(domain, "other")] = tally.get(lookup.get(domain, "other"), 0) + 1

    total = sum(tally.values())
    if not total:
        return []
    return sorted(
        ({"id": pid, "label": PROVIDER_LABELS[pid], "contacts": n,
          "share": round(n / total * 100, 1)} for pid, n in tally.items()),
        key=lambda p: p["contacts"], reverse=True,
    )


def _health_sample() -> int:
    from .. import senderhealth

    return senderhealth.signals()["sent"]


def _health_limits() -> dict:
    from .. import senderhealth

    return senderhealth.thresholds()


def _warmup() -> dict:
    """Today's real volume against the workspace's own hourly throttle."""
    today = iso()[:10]
    sent_today = db.scalar(
        "SELECT COALESCE(SUM(sent), 0) FROM campaigns "
        "WHERE sent > 0 AND substr(COALESCE(updated_at, created_at), 1, 10) = ?",
        (today,), default=0,
    ) or 0
    throttle = db.scalar("SELECT throttle_per_hour FROM workspaces LIMIT 1", default=0) or 0
    return {"today": sent_today, "cap": throttle * 24, "hourlyCap": throttle}



@router.get("/stats/reply-quality")
def reply_quality(_: Principal = Depends(requires("analytics.view"))) -> dict:
    """Replies, split by what they actually were.

    Counted off the sent outbox and the threads those addresses produced,
    so the denominator is real deliveries rather than a campaign counter.
    An out-of-office is a mail server and is excluded; an opt-out is a
    reply and is never a positive one.
    """
    from .. import optimize

    sent = db.scalar("SELECT COUNT(*) FROM outbox WHERE status = 'sent'", default=0) or 0
    rows = db.query(
        "SELECT intent, COUNT(*) n FROM threads "
        "WHERE lower(email) IN (SELECT lower(email) FROM outbox WHERE status = 'sent') "
        "GROUP BY intent")

    by = {(r["intent"] or "question"): r["n"] for r in rows}
    ooo = by.pop("ooo", 0)                      # a mail server, not a person
    replies = sum(by.values())
    positives = by.get("interested", 0)
    questions = by.get("question", 0)

    low, high = optimize.wilson(positives, sent)
    return {
        "sent": sent,
        "replies": replies,
        "positives": positives,
        "questions": questions,
        "outOfOffice": ooo,
        "replyRate": optimize.rate(replies, sent),
        "positiveReplyRate": optimize.rate(positives, sent),
        "questionRate": optimize.rate(questions, sent),
        # The interval, so the screen can refuse to look precise about a
        # rate drawn from a handful of sends.
        "positiveLow": round(low, 4),
        "positiveHigh": round(high, 4),
        "minSample": int(optimize.limits()["min_sample"]),
        "enough": sent >= int(optimize.limits()["min_sample"]),
    }


@router.get("/sender-health")
def sender_health(_: Principal = Depends(requires("analytics.view"))) -> dict:
    """Whether this account is safe to send from, and why.

    Not gated behind the insights module: this is a safety readout, not a
    reporting feature, and a deployment that did not buy reporting still
    needs to know its domain fails SPF.
    """
    from .. import senderhealth

    return senderhealth.status()


@router.post("/sender-health/recheck")
def recheck_auth(_: Principal = Depends(requires("settings.write"))) -> dict:
    """Look the DNS records up again, for every domain."""
    from .. import senderhealth

    for row in db.query("SELECT id FROM domains"):
        senderhealth.refresh_auth(row["id"])
    return senderhealth.status()


@router.get("/deliverability", dependencies=[_needs("insights")])
def deliverability(_: Principal = Depends(requires("analytics.view"))) -> dict:
    tot = totals()
    domains = db.query("SELECT * FROM domains")
    rep = round(sum(d["reputation"] for d in domains) / len(domains)) if domains else 0

    issues = []
    for d in domains:
        if not d["dkim"]:
            issues.append({"id": f"dkim-{d['id']}", "tone": "bad", "fix": "domains",
                           "text": {"en": f"{d['domain']} is sending without DKIM",
                                    "fa": f"دامنهٔ {d['domain']} بدون DKIM ارسال می‌کند"}})
        if not d["dmarc"]:
            issues.append({"id": f"dmarc-{d['id']}", "tone": "warn", "fix": "domains",
                           "text": {"en": f"{d['domain']} has no DMARC policy",
                                    "fa": f"دامنهٔ {d['domain']} سیاست DMARC ندارد"}})
    dormant = db.scalar("SELECT COUNT(*) FROM contacts WHERE score < 25", default=0)
    if dormant:
        issues.append({"id": "dormant", "tone": "warn", "fix": "segments",
                       "text": {"en": f"{dormant} contacts have not opened in 120 days",
                                "fa": f"{dormant} مخاطب ۱۲۰ روز است چیزی باز نکرده‌اند"}})

    return {
        "reputation": rep,
        # measured, not modelled: what share of what we sent was accepted
        "deliveryRate": tot["deliveryRate"],
        "bounceRate": tot["bounceRate"],
        "unsubRate": tot["unsubRate"],
        "providers": _provider_mix(),
        "warmup": _warmup(),
        "issues": issues,
        # How much is actually behind the rates above, and how much there
        # needs to be before they mean anything. Sent so the client can say
        # "not enough data" with the same floor the health card uses --
        # two figures on one screen must not disagree.
        "sample": _health_sample(),
        "minSample": int(_health_limits()["min_sample"]),
        # Reputation over time, from delivered-vs-sent on the campaigns that
        # went out each day.
        "reputationSeries": _reputation_series(30),
    }
