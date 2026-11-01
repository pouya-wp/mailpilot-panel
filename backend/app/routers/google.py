"""Connecting the mailbox the agent sends from.

The interesting route here is the callback, because it is the one endpoint in
this backend that is deliberately UNAUTHENTICATED. It has to be: Google
redirects the customer's browser to it, and a browser following a redirect
carries no Authorization header. What stands in for the token is `state` — a
random value minted when the flow starts, stored server-side, and required to
match on the way back. It is consumed on first use, so a callback URL is worth
nothing twice.

Getting that wrong is not a small bug. Without the state check, anyone can
start the flow against their OWN Google account, send the resulting callback
URL to the customer, and have the customer's panel quietly store the
attacker's refresh token — after which every campaign the business sends goes
out through a mailbox someone else reads.

The redirect URI is reported by `/google/status` rather than being documented
anywhere, because it has to be pasted into the Google Cloud console byte for
byte and a mismatch is the most common way this setup fails.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import bounces, db, deployment, google, mailer
from ..config import settings
from ..deps import Principal, requires
from ..domain import iso, log
from ..schemas import Body

router = APIRouter(prefix="/google", tags=["google"])


class ClientIn(Body):
    clientId: str = ""
    clientSecret: str = ""


class TestIn(Body):
    to: str = ""


def _origin(request: Request) -> str:
    """Where this panel is reachable from outside.

    Configured first, because behind Traefik the request's own host is the
    container's. The request is the fallback so a developer running `run.py`
    gets a working flow without setting anything.
    """
    if settings.public_url:
        return settings.public_url
    return str(request.base_url).rstrip("/")


def _panel_origin(request: Request) -> str:
    """Where the frontend UI is reachable from outside.

    In production or behind a reverse proxy, this matches public_url.
    In local development, the API runs on port 8000 and the Vite frontend runs
    on port 4300, so we redirect the user's browser back to the frontend port.
    """
    if settings.public_url:
        return settings.public_url
    host = request.url.hostname or "127.0.0.1"
    if request.url.port and request.url.port != 4300:
        return f"{request.url.scheme}://{host}:4300"
    return str(request.base_url).rstrip("/")


def redirect_uri(request: Request) -> str:
    return f"{_origin(request)}/api/google/callback"


# ==================================================================== status


@router.get("/status")
def status(request: Request, _: Principal = Depends(requires("settings.write"))) -> dict:
    out = deployment.google_status()
    out["redirectUri"] = redirect_uri(request)
    out["dailyHint"] = google.DAILY_HINT
    out["queue"] = mailer.status()
    return out


@router.put("/client")
def set_client(payload: ClientIn, principal: Principal = Depends(requires("settings.write"))) -> dict:
    """Store the OAuth client the implementer created in Google Cloud.

    An empty secret means "keep the one already installed", the same rule the
    OpenAI key follows — so re-saving this form to correct a typo in the client
    id cannot silently blank the secret.
    """
    fields: dict[str, str] = {}
    if payload.clientId:
        fields["google_client_id"] = payload.clientId.strip()
    if payload.clientSecret:
        fields["google_secret"] = payload.clientSecret.strip()
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to save")
    deployment.save_google(**fields)
    log(kind="human", actor=principal.id, action_en="updated the Google client credentials",
        action_fa="اطلاعات کلاینت گوگل به‌روزرسانی شد", target="deployment", tone="info")
    return deployment.google_status()


# ================================================================= the flow


@router.post("/connect")
def connect(request: Request, _: Principal = Depends(requires("settings.write"))) -> dict:
    """Start the handshake. Returns the URL the browser should be sent to."""
    d = deployment.get()
    if not d.get("google_client_id") or not d.get("google_secret"):
        raise HTTPException(
            status_code=400,
            detail="Add the Google OAuth client id and secret first",
        )
    state = google.new_state()
    deployment.save_google(google_state=state)
    return {
        "url": google.consent_url(
            client_id=d["google_client_id"],
            redirect_uri=redirect_uri(request),
            state=state,
        ),
        "redirectUri": redirect_uri(request),
    }


@router.get("/callback", include_in_schema=False)
def callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    """Google sends the customer's browser here.

    Every exit is a redirect back into the panel with a result in the query
    string, never a JSON body: whatever happens, the person is sitting in front
    of a browser tab and should end up looking at the panel.
    """
    # `tab=sending` matters: Settings opens on the agent tab, and the card that
    # reports the result of this redirect only exists on the sending one.
    back = f"{_panel_origin(request)}/#/settings?tab=sending"

    if error:
        return RedirectResponse(f"{back}&google=denied", status_code=303)

    expected = deployment.get().get("google_state") or ""
    # Consumed whatever happens next: a state value that survives a failed
    # attempt is a state value an attacker gets to retry against.
    deployment.save_google(google_state="")

    if not state or not expected or state != expected:
        return RedirectResponse(f"{back}&google=badstate", status_code=303)
    if not code:
        return RedirectResponse(f"{back}&google=nocode", status_code=303)

    d = deployment.get()
    try:
        tokens = google.exchange_code(
            code=code,
            client_id=d.get("google_client_id") or "",
            client_secret=d.get("google_secret") or "",
            redirect_uri=redirect_uri(request),
        )
        email = google.whoami(tokens["access_token"])
    except google.GoogleError:
        return RedirectResponse(f"{back}&google=failed", status_code=303)

    deployment.save_google(
        google_refresh=tokens["refresh_token"],
        google_email=email,
        google_connected_at=iso(),
    )
    log(kind="system", actor="google", action_en=f"connected the mailbox {email}",
        action_fa=f"صندوق {email} متصل شد", target="deployment", tone="good")
    return RedirectResponse(f"{back}&google=connected", status_code=303)


@router.post("/disconnect")
def disconnect(principal: Principal = Depends(requires("settings.write"))) -> dict:
    """Forget the mailbox.

    This does NOT revoke the grant at Google — that is the customer's to do at
    myaccount.google.com/permissions, and doing it for them from a settings
    screen would be a surprising amount of reach. Queued mail stops going out
    because there is no longer a token to send it with.
    """
    deployment.save_google(google_refresh="", google_email="", google_connected_at="",
                           google_state="", google_sync_at="")
    log(kind="human", actor=principal.id, action_en="disconnected the sending mailbox",
        action_fa="صندوق ارسال قطع شد", target="deployment", tone="warn")
    return deployment.google_status()


# ================================================================== proving it


@router.post("/test")
def test_send(payload: TestIn, principal: Principal = Depends(requires("settings.write"))) -> dict:
    """One real email, to prove the whole chain works before a campaign does.

    Defaults to the connected address, so the obvious way to use it cannot
    accidentally mail a customer.
    """
    d = deployment.get()
    if not d.get("google_refresh"):
        raise HTTPException(status_code=400, detail="No mailbox is connected")

    to = (payload.to or "").strip() or d.get("google_email") or ""
    if "@" not in to:
        raise HTTPException(status_code=400, detail="That is not an email address")

    brand = d.get("brand_name") or "MailPilot"
    try:
        token = mailer.access_token()
        raw = google.build_message(
            to=to,
            sender=d.get("from_email") or d.get("google_email") or "",
            sender_name=d.get("from_name") or brand,
            subject=f"{brand} is connected",
            html=(
                f"<p>This is a test from <strong>{brand}</strong>.</p>"
                f"<p>If you are reading it, the panel can send mail through "
                f"{d.get('google_email')}.</p>"
            ),
            reply_to=d.get("reply_to") or "",
        )
        sent = google.send_message(token, raw)
    except google.GoogleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log(kind="human", actor=principal.id, action_en=f"sent a test email to {to}",
        action_fa=f"ایمیل آزمایشی به {to} فرستاده شد", target="deployment", tone="good")
    return {"ok": True, "to": to, "messageId": sent.get("id", "")}


# =================================================================== replies


@router.post("/sync")
def sync(principal: Principal = Depends(requires("content.edit"))) -> dict:
    """Pull recent replies into the Replies screen.

    Pull rather than push: Gmail's watch API needs a Cloud Pub/Sub topic and a
    publicly reachable webhook, which is a lot of moving parts to ask a
    customer's implementer to stand up. Polling costs one request per sync and
    fails in ways that are obvious.
    """
    if not deployment.enabled("inbox"):
        raise HTTPException(status_code=404, detail="Not found")
    out = pull_replies()
    return out


def pull_replies(limit: int = 25) -> int:
    """Read new inbox mail into `threads`. Returns how many were new."""
    d = deployment.get()
    if not d.get("google_refresh"):
        raise HTTPException(status_code=400, detail="No mailbox is connected")

    since = 0
    if d.get("google_sync_at"):
        from datetime import datetime

        try:
            since = int(datetime.fromisoformat(d["google_sync_at"]).timestamp())
        except ValueError:
            since = 0

    try:
        token = mailer.access_token()
        ids = google.list_replies(token, after_epoch=since, limit=limit)
    except google.GoogleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    added, bounced, opted_out = 0, 0, 0
    for message_id in ids:
        # The Gmail message id is the thread's primary key, so a message read
        # twice by two overlapping syncs lands in the same row rather than
        # appearing twice in the operator's list.
        if db.one("SELECT 1 FROM threads WHERE id = ?", (message_id,)):
            continue
        try:
            msg = google.read_message(token, message_id)
        except google.GoogleError:
            continue

        address = google.sender_address(msg["from"])
        if not address:
            continue

        # A delivery failure is not a reply. Filed as one it sat in the
        # operator's inbox looking like a customer, and — worse — the address
        # that failed stayed subscribed and was mailed again next campaign.
        # Repeatedly sending to addresses that do not exist is what gets a
        # sending account closed.
        if bounces.is_bounce(address, msg["subject"], msg["body"]):
            permanent = bounces.is_permanent(msg["body"], msg["subject"])
            bounces.record(bounces.failed_address(msg["body"]),
                           permanent=permanent, detail=msg["subject"])
            if permanent and campaign_of(msg):
                db.execute("UPDATE campaigns SET bounces = bounces + 1 WHERE id = ?",
                           (campaign_of(msg),))
            bounced += 1
            continue

        # Someone asking to be left alone is honoured NOW, not when an
        # operator gets round to reading it. The guide promised this and the
        # code never did it: the auto-unsubscribe only fired for a thread
        # already marked `intent = unsubscribe`, and nothing ever marked one.
        if bounces.wants_out(msg["subject"], msg["body"]):
            bounces.record(address, permanent=True, detail="asked to be removed")
            db.execute("UPDATE contacts SET status='unsubscribed' WHERE lower(email) = ?",
                       (address,))
            opted_out += 1
            # still filed, so the operator can see it happened and reply if
            # they want to — removed silently is not the same as removed
            db.insert("threads", {
                "id": message_id,
                "from_en": address, "from_fa": address, "email": address,
                "subject_en": msg["subject"], "subject_fa": msg["subject"],
                "preview_en": (msg["body"] or msg["snippet"] or "").strip()[:400],
                "preview_fa": (msg["body"] or msg["snippet"] or "").strip()[:400],
                "intent": "unsubscribe", "handled": 1,
                "received_at": iso(),
            })
            continue

        name = msg["from"].split("<")[0].strip().strip('"') or address
        preview = (msg["body"] or msg["snippet"] or "").strip()[:400]

        db.insert("threads", {
            "id": message_id,
            "from_en": name, "from_fa": name,
            "email": address,
            "subject_en": msg["subject"], "subject_fa": msg["subject"],
            "preview_en": preview, "preview_fa": preview,
            # Intent and sentiment are left at their neutral defaults. The
            # triage pass that fills them in is an AI call, and running one per
            # message during a sync would turn a mailbox check into a bill.
            "received_at": iso(),
        })
        added += 1

    deployment.save_google(google_sync_at=iso())
    return {"added": added, "bounced": bounced, "optedOut": opted_out}


def campaign_of(msg: dict) -> str:
    """Which campaign a bounce refers to, if the body names one.

    Best effort. A bounce that cannot be tied to a campaign still removes the
    address, which is the part that matters — the counter is bookkeeping.
    """
    import re as _re

    found = _re.search(r"(c-[0-9a-f]{6,})", (msg.get("body") or ""))
    if not found:
        return ""
    return found.group(1) if db.one("SELECT 1 FROM campaigns WHERE id = ?",
                                    (found.group(1),)) else ""
