"""Recognising a delivery failure, and acting on it.

Without this the product had two problems that compound each other.

A bounce arrived in the Replies screen looking like a customer, so
"Delivery Status Notification (Failure)" from `mailer-daemon` sat in the
operator's inbox next to real people — noise that hides the replies worth
reading.

And the dead address stayed `subscribed`, so it was mailed again on the next
campaign, and the one after. Repeatedly sending to addresses that do not exist
is the clearest signal a mailbox provider has that a sender is working from a
bad list, and it is the thing that gets the account closed. A list only stays
clean if failures are removed from it.

HARD AND SOFT ARE NOT THE SAME. SMTP answers with a status code: 5.x.x is
permanent — no such mailbox, domain does not exist — and 4.x.x is temporary —
mailbox full, greylisted, server down for an hour. Suppressing on a temporary
failure throws away a real customer because their inbox was full on a Tuesday.
So only permanent failures suppress; temporary ones are counted and left
alone.
"""

from __future__ import annotations

import re

from . import db
from .domain import iso, log
from .security import new_id

#: Who delivery failures come from. Matched on the local part so it works
#: whatever the sending domain is.
_DAEMONS = (
    "mailer-daemon", "postmaster", "mail-daemon", "maildaemon",
    "no-reply-daemon", "bounce", "bounces",
)

#: The subjects providers use. Deliberately loose — this is one of three
#: signals, not the only one, so a false positive here is caught by the others.
_SUBJECTS = (
    "delivery status notification", "undelivered mail returned",
    "returned mail", "delivery failure", "mail delivery failed",
    "undeliverable", "failure notice", "delivery incomplete",
)

#: `5.1.1`, `550`, `5.7.1` — the permanent ones. A leading 5 means the server
#: is saying "never", not "not now".
_STATUS = re.compile(r"\b([45])\.(\d{1,3})\.(\d{1,3})\b")
_SMTP_CODE = re.compile(r"\b([45])\d{2}\b")

#: The address that failed, as providers report it.
_FAILED_FOR = re.compile(
    r"(?:final-recipient|original-recipient)\s*:\s*(?:rfc822\s*;\s*)?([^\s<>]+@[^\s<>]+)",
    re.IGNORECASE,
)
_ANY_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def is_bounce(sender: str, subject: str, body: str) -> bool:
    """Is this a delivery failure rather than a person?

    Three signals, any one of which is enough on its own: who it came from,
    what it is called, and whether it carries a delivery-status report. Real
    people do not write from `mailer-daemon`, and real replies do not contain
    `Final-Recipient: rfc822;`.
    """
    local = (sender or "").split("@")[0].lower()
    if any(d in local for d in _DAEMONS):
        return True
    subject_low = (subject or "").lower()
    if any(s in subject_low for s in _SUBJECTS):
        return True
    return "final-recipient" in (body or "").lower()


def is_permanent(body: str, subject: str) -> bool:
    """Permanent (5.x.x) or temporary (4.x.x)?

    Defaults to TEMPORARY when nothing can be read. Getting this wrong in the
    permanent direction unsubscribes a real customer because their mailbox was
    full for an afternoon, and there is no way for them to notice or complain
    — they simply stop hearing from a business they asked to hear from.
    """
    text = f"{subject or ''}\n{body or ''}"
    enhanced = _STATUS.search(text)
    if enhanced:
        return enhanced.group(1) == "5"
    code = _SMTP_CODE.search(text)
    if code:
        return code.group(1) == "5"
    return False


def failed_address(body: str, fallback: str = "") -> str:
    """Which address bounced.

    The report names it in `Final-Recipient`. Failing that, the first address
    in the body that is not the daemon itself — crude, and only used when the
    structured field is missing.
    """
    named = _FAILED_FOR.search(body or "")
    if named:
        return named.group(1).strip().strip("<>").lower()
    for candidate in _ANY_EMAIL.findall(body or ""):
        low = candidate.lower()
        if not any(d in low.split("@")[0] for d in _DAEMONS):
            return low
    return (fallback or "").lower()


def record(address: str, *, permanent: bool, detail: str = "") -> dict:
    """Mark the contact, and suppress it if the failure was permanent.

    A permanent bounce writes to the suppression list as well as the contact,
    for the same reason an unsubscribe does: suppression is what the sender
    actually consults, and it outlives the contact row.
    """
    address = (address or "").strip().lower()
    if not address or "@" not in address:
        return {"address": "", "recorded": False}

    row = db.one("SELECT id, email FROM contacts WHERE lower(email) = ?", (address,))
    with db.transaction():
        if row is not None:
            db.update("contacts", row["id"],
                      {"status": "bounced" if permanent else "subscribed"})
        if permanent and not db.one(
                "SELECT 1 FROM suppression WHERE lower(email) = ?", (address,)):
            db.insert("suppression", {
                "id": new_id("sup"), "email": address,
                "reason": "bounce", "created_at": iso(),
            })
        log(kind="system", actor="mail",
            action_en=(f"{address} bounced permanently and was suppressed"
                       if permanent else f"{address} bounced temporarily"),
            action_fa=(f"{address} برگشت خورد و مسدود شد"
                       if permanent else f"{address} موقتاً برگشت خورد"),
            target=address, tone="bad" if permanent else "warn")

    return {"address": address, "recorded": True, "permanent": permanent,
            "knownContact": row is not None, "detail": detail[:200]}


# ============================================================== opting out

#: Someone asking to be left alone, in the two languages this product ships in.
#: Deliberately unambiguous phrases only. A false positive removes a customer
#: who wanted to stay, which they never find out about and cannot complain
#: about — so a phrase that could plausibly appear in an ordinary reply does
#: not belong here. "remove" alone would match "remove the blue one from my
#: order"; "remove me" would not.
_OPT_OUT = (
    "unsubscribe", "opt out", "opt-out", "take me off", "remove me",
    "stop emailing", "stop sending", "no longer wish", "do not email",
    "don't email", "dont email", "stop contacting",
    "لغو اشتراک", "عضویت من را لغو", "دیگر ایمیل نفرست", "ایمیل نفرستید",
    "من را حذف", "مرا حذف", "حذفم کنید", "دیگه ایمیل نده", "قطع اشتراک",
)


def wants_out(subject: str, body: str) -> bool:
    """Is this reply asking to be removed?

    Read from the first part of the message only. A quoted thread underneath
    contains the previous email's own unsubscribe footer, and matching that
    would remove everybody who ever replied about anything.
    """
    text = f"{subject or ''}\n{body or ''}".lower()
    # cut at the usual quote markers before looking
    for marker in ("\n>", "\nOn ", "\n-----Original", "\nFrom:", "\n________"):
        at = text.find(marker.lower())
        if at > 0:
            text = text[:at]
    return any(phrase in text for phrase in _OPT_OUT)
