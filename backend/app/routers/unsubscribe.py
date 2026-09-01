"""The unsubscribe link, which every email is required to carry.

It was already in every message — `{{unsubscribe}}` is substituted into the
footer of every send — and it pointed at `/u/{campaign}/{contact}`, which
nothing served and which had no host on it. In a mail client a path with no
host does not resolve at all, so the link was dead twice over.

That is not a cosmetic bug.

  It is legally required. CAN-SPAM and GDPR both require a working opt-out,
  and Gmail's own bulk-sender rules require one-click unsubscribe on anything
  sent at volume.

  A reader who cannot leave presses SPAM instead, which is the single most
  damaging signal a mailbox provider takes. One complaint is worth hundreds of
  ignored emails, and the account being complained about is the customer's own
  Gmail.

THE LINK IS SIGNED. `/u/c-123/p-456` guessable means anyone can unsubscribe
anyone — a competitor could walk a customer's whole list. The token is an HMAC
over the pair, so a link works only if this server issued it.

BOTH VERBS. GET is what a person clicks. POST is what Gmail and Outlook call
themselves when the reader uses the mail client's own unsubscribe button, and
`List-Unsubscribe-Post` is what tells them they may. Without the POST the
one-click button silently does nothing.

NO AUTHENTICATION. Obviously — the person unsubscribing is a recipient, not a
user of the panel. The signature is what stands in for it.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from .. import db
from ..domain import iso, log
from ..security import blob_matches, sign_blob

router = APIRouter(tags=["unsubscribe"])


def token(campaign_id: str, contact_id: str) -> str:
    """The proof this server issued the link."""
    return sign_blob(f"unsub:{campaign_id}:{contact_id}")


def link(base: str, campaign_id: str, contact_id: str) -> str:
    """The absolute URL that goes in the email.

    Absolute because a mail client has no page to resolve a relative path
    against — the old `/u/…` was unclickable in every client that received it.
    """
    return f"{base.rstrip('/')}/u/{campaign_id}/{contact_id}/{token(campaign_id, contact_id)}"


def _page(title: str, body: str, *, ok: bool = True) -> Response:
    """A small self-contained page. No panel, no fonts, no requests.

    Whoever lands here is a recipient, not a customer: they are on a phone, in
    a mail client's browser, and they want one sentence confirming they are
    done. Anything that has to load first is a chance to fail in front of them.
    """
    accent = "#2f7d4f" if ok else "#8a3b3b"
    return Response(
        content=f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;background:#f6f7f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Tahoma,sans-serif">
<div style="max-width:520px;margin:12vh auto;padding:40px;background:#fff;border:1px solid #e8eaee;border-radius:16px;text-align:center">
  <div style="width:44px;height:44px;margin:0 auto 20px;border-radius:50%;background:{accent}"></div>
  <h1 style="margin:0 0 12px;font-size:22px;color:#16181d">{title}</h1>
  <p style="margin:0;font-size:16px;line-height:1.7;color:#6b7280">{body}</p>
</div></body></html>""",
        media_type="text/html; charset=utf-8",
    )


def _unsubscribe(campaign_id: str, contact_id: str, sig: str) -> tuple[bool, str]:
    """Do it. Returns (ok, the address) — the address only when it worked."""
    if not blob_matches(f"unsub:{campaign_id}:{contact_id}", sig):
        return False, ""

    row = db.one("SELECT id, email FROM contacts WHERE id = ?", (contact_id,))
    if row is None:
        # already deleted; nothing to do and nothing to apologise for
        return True, ""

    email = (row["email"] or "").strip().lower()
    with db.transaction():
        db.update("contacts", row["id"], {"status": "unsubscribed"})
        # BOTH, in one transaction. The suppression list is what the sender
        # actually checks, and it outlives the contact row — deleting the
        # person later must not quietly re-permit mailing them.
        if not db.one("SELECT 1 FROM suppression WHERE lower(email) = ?", (email,)):
            from ..security import new_id

            db.insert("suppression", {
                "id": new_id("sup"), "email": email,
                "reason": "unsub", "created_at": iso(),
            })
        if campaign_id:
            db.execute("UPDATE campaigns SET unsubs = unsubs + 1 WHERE id = ?", (campaign_id,))
        log(kind="system", actor="recipient", action_en=f"{email} unsubscribed",
            action_fa=f"{email} لغو اشتراک کرد", target=campaign_id or "-", tone="warn")
    return True, email


@router.get("/u/{campaign_id}/{contact_id}/{sig}", include_in_schema=False)
def unsubscribe_page(campaign_id: str, contact_id: str, sig: str) -> Response:
    """What a person gets when they click the link in the footer."""
    ok, email = _unsubscribe(campaign_id, contact_id, sig)
    if not ok:
        return _page(
            "That link did not work",
            "It may have been copied incompletely. Reply to the email and ask "
            "to be removed — a person will do it.",
            ok=False,
        )
    who = f" <strong>{email}</strong>" if email else ""
    return _page("You have been unsubscribed",
                 f"We will not email{who} again. Nothing else to do.")


@router.post("/u/{campaign_id}/{contact_id}/{sig}", include_in_schema=False)
def unsubscribe_one_click(campaign_id: str, contact_id: str, sig: str) -> Response:
    """What Gmail and Outlook call when the reader uses their own button.

    They expect a 2xx and no page — nobody sees this response. Answering 404
    here is why a one-click unsubscribe button appears to do nothing.
    """
    ok, _ = _unsubscribe(campaign_id, contact_id, sig)
    return Response(status_code=200 if ok else 400)
