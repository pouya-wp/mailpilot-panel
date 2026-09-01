"""Connecting a Gmail account, and using it.

OAuth 2.0 authorisation-code flow with offline access, then the Gmail REST API.
Standard library only, like the rest of this backend.

Three decisions worth defending.

SCOPES ARE NARROW. The obvious reading of "full access to Gmail" is
`https://mail.google.com/`, which grants deletion, settings, filters and
forwarding rules on someone's personal mailbox. This product sends campaigns
and reads the replies to them, so it asks for exactly that — `gmail.send` and
`gmail.readonly` — and nothing else. A customer looking at Google's consent
screen should be able to see that the panel cannot delete their mail, because
it genuinely cannot. Widening this is a one-line change if a feature ever earns
it; starting wide would be impossible to walk back.

THE REFRESH TOKEN IS THE CREDENTIAL. It does not expire, it is worth more than
the password, and it must never leave the server. It is stored in the
deployment row, never returned by any endpoint, and reported only as "connected
as someone@example.com".

STATE IS VERIFIED. The `state` parameter is a random value tied to one attempt
and checked on the way back. Without it, an attacker can hand a victim a
callback URL that connects the ATTACKER's mailbox to the victim's panel, and
everything the panel then sends goes through an account they control.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"

#: Send campaigns; read the replies to them. Nothing else.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
]

#: Gmail's own ceiling. A free account is ~500 recipients a day and a Workspace
#: account ~2000; going past it gets the account rate-limited, not queued.
DAILY_HINT = {"free": 500, "workspace": 2000}


class GoogleError(RuntimeError):
    """Anything the operator has to fix: consent withdrawn, quota, bad client."""


def _post_form(url: str, fields: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    return _send(req, timeout)


def _api(method: str, url: str, token: str, payload: dict | None = None,
         timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return _send(req, timeout)


def _send(req, timeout: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise GoogleError(_explain(exc.code, exc.read().decode("utf-8", "replace"))) from exc
    except urllib.error.URLError as exc:
        raise GoogleError(f"Could not reach Google: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise GoogleError(f"Could not reach Google: {exc}") from exc


#: Google's own wording is accurate but written for whoever wrote the code, not
#: for whoever has to fix it. These are the failures an operator actually hits,
#: rewritten as the action that clears them. Matched on the machine-readable
#: `reason`/status rather than on the prose, which is not stable.
_ADVICE = {
    "accessNotConfigured": (
        "The Gmail API is not switched on in your Google Cloud project. Open "
        "the project, go to APIs & Services -> Library, enable 'Gmail API', "
        "then wait a minute or two and try again."
    ),
    "insufficientPermissions": (
        "The connected account did not grant permission to send. Disconnect it "
        "and connect again, accepting every box on Google's screen."
    ),
    "rateLimitExceeded": (
        "Google is rate-limiting this account. Sending will resume on its own; "
        "nothing queued has been lost."
    ),
    "dailyLimitExceeded": (
        "This account has hit Google's daily sending limit — about 500 a day on "
        "a personal account, 2000 on Workspace. The rest goes out tomorrow."
    ),
    "invalid_grant": (
        "Google no longer accepts the saved authorisation. Reconnect the "
        "mailbox in Settings -> Sending."
    ),
    "forbiddenForServiceAccounts": (
        "This is a service account. Connect an ordinary Google account instead."
    ),
}


def _explain(code: int, body: str) -> str:
    """A sentence a person can act on, not a wall of JSON.

    Google answers with a nested error document. Printing it raw put four
    hundred characters of braces in a toast — the useful sentence was in
    there, wrapped past legibility and, in a right-to-left panel, shuffled.
    """
    message, reason = "", ""
    try:
        payload = json.loads(body) or {}
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")
            details = error.get("errors") or []
            if details and isinstance(details[0], dict):
                reason = str(details[0].get("reason") or "")
            reason = reason or str(error.get("status") or "")
        elif isinstance(error, str):
            # the token endpoint answers with a flat {"error": "invalid_grant"}
            reason = error
            message = str(payload.get("error_description") or "")
    except (ValueError, TypeError):
        pass

    advice = _ADVICE.get(reason)
    if advice:
        return advice
    if message:
        # Google's own sentence, trimmed of the "Enable it by visiting <url>"
        # tail that a toast cannot render usefully anyway.
        return f"Google refused this ({code}): {message.strip()}"
    return f"Google returned {code} and no explanation."


# ============================================================== the handshake


def new_state() -> str:
    """One-use, unguessable, and checked on the way back.

    Skipping this is how a panel ends up sending through a mailbox the attacker
    controls: they start the flow, hand the victim the callback URL, and the
    victim's panel stores the attacker's tokens.
    """
    return secrets.token_urlsafe(24)


def consent_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # offline + consent is what returns a REFRESH token. Without them the
        # panel gets an hour of access and then silently stops sending.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    })


def exchange_code(*, code: str, client_id: str, client_secret: str,
                  redirect_uri: str) -> dict[str, Any]:
    out = _post_form(TOKEN_URL, {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    if not out.get("refresh_token"):
        raise GoogleError(
            "Google did not return a refresh token. Remove this app at "
            "myaccount.google.com/permissions and connect again."
        )
    return out


def refresh_access(*, refresh_token: str, client_id: str, client_secret: str) -> dict[str, Any]:
    """Trade the long-lived credential for an hour of access."""
    return _post_form(TOKEN_URL, {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    })


def whoami(access_token: str) -> str:
    return str(_api("GET", USERINFO, access_token).get("email") or "")


# =================================================================== sending


def build_message(*, to: str, sender: str, sender_name: str, subject: str,
                  html: str, text: str = "", reply_to: str = "",
                  headers: dict[str, str] | None = None) -> str:
    """A MIME message, base64url encoded the way Gmail wants it.

    Sent as multipart/alternative with a text part. A campaign that is HTML only
    reads as spam to several filters and is unreadable in a client that refuses
    HTML — and the plain part costs nothing to include.
    """
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    for key, value in (headers or {}).items():
        msg[key] = value

    msg.set_content(text or _strip_tags(html))
    msg.add_alternative(html, subtype="html")

    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def send_message(access_token: str, raw: str) -> dict[str, Any]:
    return _api("POST", f"{GMAIL}/messages/send", access_token, {"raw": raw})


def _strip_tags(html: str) -> str:
    """A readable plain-text part from the HTML, without a dependency.

    Deliberately crude: block elements become newlines, everything else goes.
    It is a fallback body, not a rendering.
    """
    import re

    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html or "")
    text = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</h[1-6]>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# =================================================================== reading


def list_replies(access_token: str, *, after_epoch: int = 0, limit: int = 25) -> list[str]:
    """Message ids of recent inbox mail, newest first.

    `after` rather than a stored page token: the panel wants "anything since I
    last looked", and a token would go stale the moment a sync was missed.
    """
    query = "in:inbox"
    if after_epoch:
        query += f" after:{int(after_epoch)}"
    url = f"{GMAIL}/messages?" + urllib.parse.urlencode({"q": query, "maxResults": limit})
    out = _api("GET", url, access_token)
    return [m["id"] for m in out.get("messages") or []]


def read_message(access_token: str, message_id: str) -> dict[str, Any]:
    """One message, flattened to what a reply row needs."""
    out = _api("GET", f"{GMAIL}/messages/{message_id}?format=full", access_token)
    headers = {h["name"].lower(): h["value"]
               for h in (out.get("payload") or {}).get("headers") or []}
    return {
        "id": out.get("id"),
        "threadId": out.get("threadId"),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "snippet": out.get("snippet", ""),
        "body": _body_text(out.get("payload") or {}),
        "at": int(out.get("internalDate", 0)) // 1000,
    }


def _body_text(payload: dict) -> str:
    """Depth-first for the first text/plain part, falling back to HTML.

    A Gmail payload is a tree: multipart/alternative inside multipart/mixed
    inside whatever the sender's client felt like producing.
    """
    mime = payload.get("mimeType", "")
    data = (payload.get("body") or {}).get("data")

    if mime == "text/plain" and data:
        return _decode(data)
    for part in payload.get("parts") or []:
        found = _body_text(part)
        if found:
            return found
    if mime == "text/html" and data:
        return _strip_tags(_decode(data))
    return ""


def _decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


def sender_address(from_header: str) -> str:
    """`Ali <ali@example.com>` -> `ali@example.com`, or empty.

    The `@` check is not belt-and-braces: `parseaddr` returns the first token
    of anything it cannot parse, so a malformed From header yields a word. That
    word would otherwise be written into `threads.email` and shown to an
    operator as the person who replied.
    """
    from email.utils import parseaddr

    address = (parseaddr(from_header)[1] or "").lower().strip()
    return address if "@" in address else ""
