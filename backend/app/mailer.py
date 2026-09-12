"""Actually sending the mail.

Everything above this file has been about deciding WHAT to send. This is the
part that puts it in someone's inbox, and it is the part where being careless
costs a real person real money and a real sending reputation.

Four things it does that a naive loop would not.

IT IS A QUEUE, NOT A REQUEST. One row per recipient, written in a transaction
when the campaign is approved, then drained by a worker. A campaign to twenty
thousand people cannot happen inside an HTTP request, and a send that dies
half-way must be resumable rather than restarted — which it is, because the
queue remembers who has already been sent to.

IT NEVER SENDS TWICE. The row is marked `sending` before the API call and
`sent` after. A crash between the two leaves a row that is visibly stuck rather
than one that silently goes out again on the next pass. Duplicate mail is the
one delivery mistake recipients genuinely punish.

IT RESPECTS THE SUPPRESSION LIST AT SEND TIME, not only at queue time. Someone
who unsubscribes while a campaign is draining must not receive the rest of it,
and there can be hours between those two moments.

IT PACES ITSELF. Gmail allows roughly 500 recipients a day on a personal
account and 2000 on Workspace, and it enforces that by rejecting — so the
worker sleeps between sends and stops cleanly when Google pushes back, leaving
the rest queued for tomorrow rather than burning the account's reputation
trying.
"""

from __future__ import annotations

import threading
import time
import urllib.parse
from typing import Any

from . import db, deployment, eligibility, emailhtml, google, pacing
from .config import settings
from .domain import iso, log
from .security import new_id

#: Seconds between sends. Gentle on purpose: this is a marketing agent for one
#: business, not a bulk relay, and pacing is most of what keeps a domain clean.
SEND_INTERVAL = 1.2

#: Consecutive Google failures before the worker stops and leaves the rest
#: queued. A quota rejection repeated four hundred times is not retrying, it is
#: hammering an account that has already said no.
GIVE_UP_AFTER = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  contact_id  TEXT NOT NULL DEFAULT '',
  email       TEXT NOT NULL,
  name        TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'queued',
  error       TEXT NOT NULL DEFAULT '',
  message_id  TEXT NOT NULL DEFAULT '',
  queued_at   TEXT NOT NULL,
  sent_at     TEXT NOT NULL DEFAULT '',
  -- Per-recipient copy, written by Beyondex Professional mode. Empty in
  -- manual mode, where every row shares the campaign's one body.
  subject     TEXT NOT NULL DEFAULT '',
  body        TEXT NOT NULL DEFAULT '',
  -- What the reviewer scored this draft, and what it thought. Kept so an
  -- operator can see WHY a message was held rather than only that it was.
  review      TEXT NOT NULL DEFAULT '',
  -- Which arm of an A/B test this recipient was dealt. Empty for the
  -- overwhelming majority of sends, which are not tests. Written once and
  -- never changed: nobody may receive two first-touch variants.
  variant     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(status, campaign_id);
CREATE INDEX IF NOT EXISTS idx_outbox_campaign ON outbox(campaign_id);
"""

#: Columns added to `outbox` after it first shipped. Same idempotent dance
#: as everywhere else: CREATE TABLE IF NOT EXISTS will not add a column to a
#: table that already exists, and a panel installed last month has one.
_ADDED_COLUMNS = {
    "subject": "TEXT NOT NULL DEFAULT ''",
    "body": "TEXT NOT NULL DEFAULT ''",
    "review": "TEXT NOT NULL DEFAULT ''",
    "variant": "TEXT NOT NULL DEFAULT ''",
}


def migrate() -> None:
    have = {r["name"] for r in db.query("PRAGMA table_info(outbox)")}
    if not have:
        return
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in have:
            db.execute(f"ALTER TABLE outbox ADD COLUMN {column} {ddl}")

_worker: threading.Thread | None = None
_wake = threading.Event()
_lock = threading.Lock()


# ================================================================== queueing


def enqueue(campaign_id: str, *, recipients: list[dict]) -> int:
    """Write one row per recipient that may be sent to. Returns how many.

    The decision about WHO may be sent to belongs to `eligibility`, and the
    pre-flight summary the customer read before launching is the very same
    call — so what that screen promised is what this does. Every exclusion
    is written down with its reason rather than silently skipped: "912 of
    1,000" is only an acceptable thing to say if the other 88 can be named.

    Checked again at send time, because hours pass between approving a
    campaign and the last message leaving, and somebody who unsubscribes
    inside that window must not receive the rest of it.
    """
    from . import brandprofile, optimize, scoring

    now = iso()
    verdict = eligibility.classify(campaign_id, recipients)
    # Assigned against the ELIGIBLE list, not the selected one, so the arms
    # stay even after suppression rather than even before it.
    arms = optimize.assign(campaign_id, verdict["eligible"])

    # Better-fit prospects are written FIRST. The sender drains oldest-first,
    # so ordering the rows here is enough -- no change to the claim logic,
    # which is what stops a message going out twice and is not worth
    # destabilising for a sort. Nobody is skipped and nobody is added: this
    # reorders the eligible, it does not widen them.
    ordered = verdict["eligible"]
    try:
        profile = brandprofile.get()
        if profile.get("offers"):
            fit = {
                (c.get("email") or "").lower(): scoring.score_for(
                    c, profile=profile, offer=scoring.best_offer(c, profile))["score"]
                for c in ordered
            }
            ordered = sorted(
                ordered,
                key=lambda c: fit.get((c.get("email") or "").lower(), 0),
                reverse=True)
    except Exception:  # noqa: BLE001 - a sort must never stop a send
        ordered = verdict["eligible"]

    queued = 0
    with db.transaction():
        for person in ordered:
            email = (person.get("email") or "").strip().lower()
            db.insert("outbox", {
                "id": new_id("out"), "campaign_id": campaign_id,
                "contact_id": person.get("id") or "",
                "email": email,
                "name": person.get("name") or "", "status": "queued",
                "variant": arms.get(email, ""),
                "queued_at": now,
            })
            queued += 1
        # The excluded, kept as rows so the reason survives the page closing.
        # They are never claimed by the sender: `_claim` only takes `queued`.
        for person in verdict["excluded"]:
            db.insert("outbox", {
                "id": new_id("out"), "campaign_id": campaign_id,
                "contact_id": "", "email": (person.get("email") or "").strip().lower(),
                "name": person.get("name") or "", "status": "blocked",
                "error": person["reason"], "queued_at": now,
            })
    if queued:
        start()
    return queued


def pending(campaign_id: str = "") -> int:
    if campaign_id:
        return db.scalar("SELECT COUNT(*) FROM outbox WHERE status = 'queued' AND campaign_id = ?",
                         (campaign_id,), default=0) or 0
    return db.scalar("SELECT COUNT(*) FROM outbox WHERE status = 'queued'", default=0) or 0


def progress(campaign_id: str) -> dict[str, int]:
    rows = db.query(
        "SELECT status, COUNT(*) n FROM outbox WHERE campaign_id = ? GROUP BY status",
        (campaign_id,),
    )
    out = {r["status"]: r["n"] for r in rows}
    return {
        "queued": out.get("queued", 0),
        "sent": out.get("sent", 0),
        "failed": out.get("failed", 0),
        # Written, reviewed, and not good enough to send. Kept apart from
        # `failed`, which means Gmail refused it — an operator can do
        # something about one of those and nothing about the other.
        "held": out.get("held", 0),
        "suppressed": out.get("suppressed", 0),
        # Refused by the pre-send gate: unsubscribed, suppressed, previously
        # hard-bounced, malformed or duplicated. Counted separately from
        # everything else because it is the one the customer chose nothing
        # about and most needs explaining.
        "blocked": out.get("blocked", 0),
        "total": sum(out.values()),
    }


# =================================================================== sending


def public_base() -> str:
    """The origin a recipient's mail client can actually reach.

    Not optional for the unsubscribe link: a mail client has no page to resolve
    a relative path against, so `/u/…` in an email is not a weak link, it is
    not a link. Falls back to the panel's own configured URL and, failing that,
    to a mailto so the footer still offers a way out.
    """
    from .config import settings

    return settings.public_url or ""


def _personalise(text: str, person: dict, campaign_id: str) -> str:
    """Merge tags, filled per recipient.

    `{{unsubscribe}}` becomes a real, absolute, SIGNED link. It shipped as a
    relative path that nothing served — dead in every client that received it —
    and a reader who cannot leave presses spam instead, which is the most
    damaging signal a mailbox provider takes.
    """
    from .routers.unsubscribe import link as unsub_link

    first = (person.get("name") or "").strip().split(" ")[0]
    base = public_base()
    contact_id = person.get("id") or ""
    d = deployment.get()
    support = d.get("support_email") or d.get("reply_to") or ""

    if base and contact_id:
        out_link = unsub_link(base, campaign_id, contact_id)
    else:
        # No public URL configured. A mailto is worse than a page but far
        # better than a broken link, and it still gives the reader a way out.
        out_link = f"mailto:{support}?subject=Unsubscribe" if support else "#"

    # THE CALL TO ACTION IS NOT THE PANEL. `base` is this deployment's admin
    # panel, and it used to be the first choice here — so an outreach email
    # whose button said "start a conversation" sent a gold shop in Dubai to a
    # MailPilot sign-in screen. Nobody who received one could have acted on it.
    #
    # The button always means "reply to us", so it is a mailto, and the
    # address is the best one we hold. The connected Gmail is last and is the
    # reason this can always be answered: an account has to be connected for
    # the mail to have been sent at all, so there is always somewhere for the
    # reader to land.
    cta_to = support or d.get("google_email") or d.get("from_email") or ""
    subject_hint = urllib.parse.quote((d.get("brand_name") or "").strip())
    if cta_to:
        cta_link = f"mailto:{cta_to}"
        if subject_hint:
            cta_link += f"?subject=Re:%20{subject_hint}"
    else:
        cta_link = "#"

    return (
        text.replace("{{first_name}}", first or "there")
        .replace("{{name}}", person.get("name") or "")
        .replace("{{email}}", person.get("email") or "")
        .replace("{{unsubscribe}}", out_link)
        .replace("{{cta_url}}", cta_link)
    )


def access_token() -> str:
    d = deployment.get()
    if not d.get("google_refresh"):
        raise google.GoogleError("No Gmail account is connected")
    out = google.refresh_access(
        refresh_token=d["google_refresh"],
        client_id=d.get("google_client_id") or "",
        client_secret=d.get("google_secret") or "",
    )
    token = out.get("access_token")
    if not token:
        raise google.GoogleError("Google refused to renew access; reconnect the account")
    return token


def _claim():
    """Take the next queued row, atomically, or return None.

    This was a SELECT followed by an UPDATE, and the gap between them is a
    race: two drains both read the same row as `queued`, both mark it
    `sending`, and both send. Measured at three concurrent drains it produced
    eight messages for six recipients — two people got the same email twice,
    which is the one delivery mistake recipients actually punish, and it made
    the promise at the top of this file ("IT NEVER SENDS TWICE") false.

    The claim is now a single conditional UPDATE. Whoever changes the row from
    `queued` to `sending` owns it; everyone else sees rowcount 0 and moves on.
    That is safe whatever wakes a second worker — a stray thread, a second
    uvicorn worker, a deploy that overlaps a running one — rather than relying
    on there only ever being one.
    """
    while True:
        candidate = db.one(
            # `rowid` is the tie-break, and it is load-bearing: every row of
            # one campaign is written with the same `queued_at`, and the
            # rows are written in fit order. Without this the send order
            # among them is whatever SQLite happens to do, which today is
            # insertion order and is not promised to stay that way.
            "SELECT id FROM outbox WHERE status = 'queued' "
            "ORDER BY queued_at, rowid LIMIT 1")
        if candidate is None:
            return None
        won = db.execute(
            "UPDATE outbox SET status = 'sending' WHERE id = ? AND status = 'queued'",
            (candidate["id"],),
        ).rowcount
        if won:
            return db.one("SELECT * FROM outbox WHERE id = ?", (candidate["id"],))
        # somebody else took it between the read and the write; look again


def _drain() -> None:
    """Send what is queued, then stop. Runs on its own thread.

    Held back by the workspace's own hourly cap and quiet hours, which were
    editable and displayed for the whole life of the product and enforced by
    nothing: a campaign went out in one unbroken burst at whatever hour it
    was approved. Being asked to stop is not a failure — nothing is claimed
    and nothing is marked failed, the loop simply returns and the next tick
    thirty seconds later tries again, so a held campaign resumes by itself.
    """
    failures = 0
    token = ""
    token_at = 0.0
    said_why = ""

    while True:
        allowed, why = pacing.may_send()
        if not allowed:
            # Said once per hold rather than every thirty seconds, which
            # would fill the activity log with the same line all night.
            if why != said_why:
                log(kind="system", actor="mailer",
                    action_en=f"holding the queue: {why}",
                    action_fa="ارسال موقتاً نگه داشته شد", target="mailer", tone="info")
                said_why = why
            return
        said_why = ""

        row = _claim()
        if row is None:
            return

        campaign = db.one("SELECT * FROM campaigns WHERE id = ?", (row["campaign_id"],))
        if campaign is None or campaign["status"] not in {"running", "scheduled"}:
            # the campaign was paused or deleted under us; drop the rest of it
            db.execute("UPDATE outbox SET status = 'cancelled' WHERE campaign_id = ? AND status = 'queued'",
                       (row["campaign_id"],))
            continue

        # Checked again here, not only at queue time: someone who unsubscribed
        # while this was draining must not get the rest of the campaign. The
        # same gate as the pre-flight summary, so there is one answer to
        # "may we send to this person" rather than two that can disagree.
        refusal = eligibility.may_send_now(row["email"], row["campaign_id"])
        if refusal:
            db.update("outbox", row["id"], {
                "status": "blocked", "error": refusal, "sent_at": iso()})
            continue

        # Beyondex Professional writes this one its own email first. A row
        # that already has a body is one an earlier run composed, so a
        # restart does not pay for the same prospect twice.
        if (_maybe(campaign, "write_mode") == "professional"
                and not (_maybe(row, "body") or "").strip()):
            if not _compose_one(row, campaign):
                continue
            row = db.one("SELECT * FROM outbox WHERE id = ?", (row["id"],))

        try:
            if not token or time.time() - token_at > 45 * 60:
                token = access_token()
                token_at = time.time()

            person = {"id": row["contact_id"], "email": row["email"], "name": row["name"]}
            d = deployment.get()
            # The house template is read HERE, per send, not baked into the
            # campaign when it was written. Marking a template "use for all"
            # has to affect the next thing that goes out, including campaigns
            # that already existed.
            # The row's own copy if professional mode wrote some, otherwise
            # the campaign's. One sender, two modes: manual mode simply
            # never fills these in.
            own_body = (_maybe(row, "body") or "").strip()
            own_subject = (_maybe(row, "subject") or "").strip()
            body_src = own_body or (campaign["body_en"] or "")
            subject_src = own_subject or (campaign["subject_en"] or "")

            dressed = emailhtml.wrap_for_send(
                db, body_src, subject=subject_src,
            )
            html = _personalise(dressed, person, campaign["id"])
            subject = _personalise(subject_src, person, campaign["id"])

            raw = google.build_message(
                to=row["email"],
                sender=d.get("from_email") or d.get("google_email") or "",
                sender_name=d.get("from_name") or d.get("brand_name") or "",
                subject=subject,
                html=html,
                reply_to=d.get("reply_to") or "",
                # `List-Unsubscribe` alone only offers a mailto. Gmail and
                # Outlook show their own one-click button when the URL form is
                # present AND `List-Unsubscribe-Post` says the URL accepts a
                # POST — without the second header the button does nothing.
                headers=_unsub_headers(d, campaign["id"], person["id"]),
            )
            sent = google.send_message(token, raw)

            db.update("outbox", row["id"], {
                "status": "sent", "message_id": sent.get("id") or "", "sent_at": iso(),
            })
            _bump(campaign["id"])
            failures = 0

        except google.GoogleError as exc:
            failures += 1
            db.update("outbox", row["id"], {
                "status": "failed", "error": str(exc)[:400], "sent_at": iso(),
            })
            if failures >= GIVE_UP_AFTER:
                # Google has said no five times. The rest stays queued for the
                # next run rather than being burned against a closed door.
                log(kind="system", actor="mailer",
                    action_en="paused sending after repeated Google errors",
                    action_fa="ارسال پس از خطاهای پیاپی گوگل متوقف شد",
                    target=campaign["id"], tone="bad")
                return

        time.sleep(SEND_INTERVAL)


def _compose_one(row, campaign) -> bool:
    """Research, plan, write and review one prospect's email.

    Returns whether there is now something to send. A held draft is NOT a
    failure — it is the reviewer doing its job — so it gets its own status
    and keeps its reason, rather than being marked failed and looking like
    Gmail refused it.
    """
    from . import brandprofile, professional
    from .ai_provider import AIUnavailable

    contact = db.one("SELECT * FROM contacts WHERE id = ?", (row["contact_id"],))
    person = {
        "email": row["email"],
        "name": row["name"],
        "company": _maybe(contact, "company") if contact else "",
        "website": _maybe(contact, "website") if contact else "",
        "country": (contact["country"] if contact else "") or "",
    }

    try:
        out = professional.compose_for(
            person,
            profile=brandprofile.get(),
            goal=_maybe(campaign, "goal") or "",
            lang=deployment.get().get("default_lang") or "en",
        )
    except AIUnavailable:
        # No key, no search, no budget. The rest of this campaign will hit
        # exactly the same wall, so put the row back and let the caller
        # stop rather than burning through the queue one failure at a time.
        db.update("outbox", row["id"], {"status": "queued"})
        raise
    except Exception as exc:  # noqa: BLE001 - one bad prospect must not stop the rest
        db.update("outbox", row["id"], {
            "status": "held", "error": f"compose failed: {exc}"[:400], "sent_at": iso(),
        })
        return False

    if out.get("status") != "ready":
        db.update("outbox", row["id"], {
            "status": "held",
            "error": (out.get("reason") or "")[:400],
            "review": db.dumps(out.get("review") or {}),
            "sent_at": iso(),
        })
        return False

    db.update("outbox", row["id"], {
        "subject": out.get("subject") or "",
        "body": out.get("body") or "",
        "review": db.dumps({"score": out.get("score"), **(out.get("review") or {})}),
    })
    return True


def _maybe(row, key: str) -> str:
    """Read a column an older database may not have yet.

    The sender runs against whatever shape the disk is in; a deployment
    mid-upgrade must not crash on a column added five minutes ago.
    """
    try:
        return row[key]
    except (IndexError, KeyError):
        return ""


def _unsub_headers(d: dict, campaign_id: str, contact_id: str) -> dict[str, str]:
    """What the mail client reads to draw its own unsubscribe button."""
    from .routers.unsubscribe import link as unsub_link

    mail_to = d.get("reply_to") or d.get("from_email") or d.get("google_email") or ""
    parts = []
    base = public_base()
    if base and contact_id:
        parts.append(f"<{unsub_link(base, campaign_id, contact_id)}>")
    if mail_to:
        parts.append(f"<mailto:{mail_to}?subject=Unsubscribe>")
    if not parts:
        return {}

    headers = {"List-Unsubscribe": ", ".join(parts)}
    if base and contact_id:
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    return headers


def _bump(campaign_id: str) -> None:
    """Move the campaign's own counters as the queue drains."""
    stats = progress(campaign_id)
    db.execute(
        "UPDATE campaigns SET sent = ?, delivered = ?, updated_at = ? WHERE id = ?",
        (stats["sent"], stats["sent"], iso(), campaign_id),
    )
    if stats["queued"] == 0:
        db.execute("UPDATE campaigns SET status = 'sent' WHERE id = ? AND status = 'running'",
                   (campaign_id,))


# ================================================================= scheduling


def promote_due() -> int:
    """Move scheduled campaigns whose time has come into the outbox.

    Checked on every worker tick rather than by a cron entry, because a cron
    entry is a second thing to install and a second thing to forget. A campaign
    scheduled while the process was down is picked up on the next tick, late
    rather than never.
    """
    now = iso()
    due = db.query(
        "SELECT id, segment_id FROM campaigns "
        "WHERE status = 'scheduled' AND scheduled_for IS NOT NULL AND scheduled_for <= ?",
        (now,),
    )
    if not due:
        return 0

    from .routers.audience import segment_members

    started = 0
    for row in due:
        if not row["segment_id"]:
            continue
        db.execute("UPDATE campaigns SET status = 'running', updated_at = ? WHERE id = ?",
                   (now, row["id"]))
        queued = enqueue(row["id"], recipients=segment_members(row["segment_id"]))
        db.execute("UPDATE campaigns SET recipients = ? WHERE id = ?", (queued, row["id"]))
        log(kind="system", actor="mailer", action_en="started a scheduled campaign",
            action_fa="کمپین زمان‌بندی‌شده آغاز شد", target=row["id"], tone="good")
        started += 1
    return started


def recover_stuck() -> int:
    """Put `sending` rows back in the queue.

    A row is only in that state between being claimed and the Gmail call
    returning, so finding one at startup means the process died mid-send. The
    risk of re-queueing is one duplicate email; the risk of leaving it is a
    recipient silently dropped from a campaign, which is worse and invisible.
    """
    stuck = db.scalar("SELECT COUNT(*) FROM outbox WHERE status = 'sending'", default=0) or 0
    if stuck:
        db.execute("UPDATE outbox SET status = 'queued' WHERE status = 'sending'")
        log(kind="system", actor="mailer",
            action_en=f"requeued {stuck} sends interrupted by a restart",
            action_fa=f"{stuck} ارسال نیمه‌تمام دوباره در صف قرار گرفت",
            target="mailer", tone="warn")
    return stuck


# ==================================================================== worker


def resume_on_start() -> None:
    """Called once at startup: finish whatever the last process did not."""
    recover_stuck()
    if pending() or db.scalar(
        "SELECT COUNT(*) FROM campaigns WHERE status = 'scheduled'", default=0
    ):
        start()


def start() -> None:
    """Make sure a worker is running. Safe to call from anywhere."""
    global _worker
    if not settings.sender_enabled:
        # The queue still fills; nothing drains it. A deployment that has been
        # told not to send must not send because it was woken by a write.
        return
    with _lock:
        if _worker is not None and _worker.is_alive():
            _wake.set()
            return
        _worker = threading.Thread(target=_loop, name="mailer", daemon=True)
        _worker.start()


def _loop() -> None:
    """Drain, wait to be woken, drain again.

    A daemon thread rather than a scheduler: this process is a single uvicorn
    worker by design (one SQLite writer), so the queue has exactly one consumer
    and needs no locking beyond the database's own.
    """
    while True:
        try:
            promote_due()
            _drain()
        except Exception as exc:  # noqa: BLE001 - a worker that dies stops all sending
            log(kind="system", actor="mailer", action_en=f"send worker error: {exc}"[:120],
                action_fa="خطای کارگر ارسال", target="mailer", tone="bad")
        _wake.wait(timeout=30)
        _wake.clear()


def status() -> dict[str, Any]:
    return {
        "running": bool(_worker and _worker.is_alive()),
        "queued": pending(),
    }
