"""How well one prospect fits one offer.

WHY THIS IS NOT AN AI CALL. The obvious implementation asks a model to
score each prospect. At pre-flight that means a web search and a
completion for every one of a thousand selected contacts before the
customer has agreed to send anything — minutes of waiting and a real bill,
to produce a number. Worse, the "reasons" would be model prose, which
reads like evidence and is not.

So this is arithmetic over things already known: what the Brand Profile
says the business sells and to whom, and what the contact record actually
carries — company, website, country, and the tags the email finder wrote
when it found them. Every reason is therefore a fact that can be pointed
at, and the whole thing runs over a thousand contacts in milliseconds.

FIT AND CONFIDENCE ARE DIFFERENT NUMBERS. A business with one thin page
may be a perfect match that we happen to know little about. Collapsing
those into one score punishes obscurity, which §16.2 forbids and which
would systematically deprioritise exactly the small businesses this
product is sold to. `research_confidence` is reported beside the fit
score and never subtracted from it.

SCORING DOES NOT GRANT PERMISSION. A suppressed contact with a fit of 95
is still not sendable. Eligibility is decided in `eligibility.py` and this
module cannot overrule it; the two are combined at the call site, where a
block always wins.

NOTHING SENSITIVE. The only inputs are business attributes — industry,
location, what they sell, what they publish. There is no inference about
any person, and the fields this reads are listed in `INPUTS` so that the
claim is checkable rather than merely asserted.
"""

from __future__ import annotations

import re
from typing import Any

from . import db
from .domain import iso
from .security import new_id

#: Bump when the meaning of a score changes, so an old score stays
#: interpretable next to a new one rather than being silently compared.
SCORE_VERSION = "v1"

#: Every field this module is allowed to read about a prospect. Written
#: down so "no sensitive attributes are used" is a thing a reader can
#: verify in ten seconds instead of taking on trust. A test asserts that
#: nothing outside this list is touched.
INPUTS = ("company", "website", "country", "tags", "source_en", "email", "name_en")

SCHEMA = """
CREATE TABLE IF NOT EXISTS prospect_scores (
  id            TEXT PRIMARY KEY,
  campaign_id   TEXT NOT NULL,
  contact_id    TEXT NOT NULL,
  score         INTEGER NOT NULL DEFAULT 0,
  band          TEXT NOT NULL DEFAULT 'LOW_FIT',
  confidence    REAL NOT NULL DEFAULT 0,
  best_offer    TEXT NOT NULL DEFAULT '',
  reasons       TEXT NOT NULL DEFAULT '[]',
  risks         TEXT NOT NULL DEFAULT '[]',
  score_version TEXT NOT NULL DEFAULT 'v1',
  -- The score as it was when the message actually went out. The live score
  -- may move afterwards as research improves; history must not.
  sent_snapshot TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pscore_pair
  ON prospect_scores(campaign_id, contact_id);
"""

#: The bands, in the order they are tested. From §16.3.
BANDS = (
    (85, "HIGH_FIT"),
    (70, "GOOD_FIT"),
    (50, "MEDIUM_FIT"),
    (0, "LOW_FIT"),
)

#: What each band is allowed to do by default. Low fit is excluded unless
#: the customer says otherwise, which is §16.6.
DEFAULT_INCLUDED = {"HIGH_FIT", "GOOD_FIT"}


def band_for(score: int) -> str:
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "LOW_FIT"


def _words(text: str) -> set[str]:
    """Meaningful words, lowercased. Crude and deliberately so.

    This is a keyword overlap, not a semantic model, and pretending
    otherwise would be the whole problem with this feature. Short words are
    dropped because "a", "of" and "the" overlap between any two sentences
    and would make everything look like a match.
    """
    return {w for w in re.split(r"[^\w؀-ۿ]+", (text or "").lower())
            if len(w) > 3}


def _affinity(a: set[str], b: set[str], saturate: int = 3) -> float:
    """How strongly two descriptions overlap, 0..1.

    Counts SHARED MEANINGFUL WORDS and saturates, rather than dividing by
    the length of `b`. Dividing would mean a longer ideal-customer
    description scores every prospect lower — writing more about your best
    customer should not make everybody fit worse — and nobody ever matches
    every word of a phrase anyway.

    `saturate` is where "clearly related" tops out. Beyond a few shared
    words this is not able to tell degrees apart, and pretending otherwise
    is how a keyword count starts being read as a semantic model.
    """
    if not a or not b:
        return 0.0
    return min(1.0, len(a & b) / max(1, saturate))


def _contact_words(contact: dict) -> set[str]:
    """Everything we know about this business, as words."""
    parts = [
        str(contact.get("company") or ""),
        str(contact.get("name_en") or contact.get("name") or ""),
        str(contact.get("source_en") or ""),
        " ".join(str(t) for t in _tags(contact)),
    ]
    return _words(" ".join(parts))


def _tags(contact: dict) -> list:
    """Tags, whichever shape they arrive in — a JSON string from the row,
    or a list from a caller that has already decoded it."""
    tags = contact.get("tags")
    if isinstance(tags, str):
        return db.loads(tags, [])
    return tags or []


def _place_words(contact: dict) -> set[str]:
    """Where this business is, as far as we know."""
    return _words(f"{contact.get('country') or ''} "
                  f"{' '.join(str(t) for t in _tags(contact))}")


def confidence_for(contact: dict) -> float:
    """How much we actually know, 0..1 — kept apart from fit on purpose.

    A prospect we know nothing about is not a bad prospect; it is an
    unknown one, and the difference matters because the fix for one is to
    drop them and the fix for the other is to look them up.
    """
    have = 0.0
    if str(contact.get("website") or "").strip():
        have += 0.45          # the strongest single signal we can hold
    if str(contact.get("company") or "").strip():
        have += 0.2
    if str(contact.get("country") or "").strip():
        have += 0.15
    if _tags(contact):
        have += 0.2
    return round(min(1.0, have), 2)


def score_for(contact: dict, *, profile: dict, offer: dict | None = None,
              region: str = "") -> dict[str, Any]:
    """Fit of one prospect for one offer, with the reasons that produced it.

    The offer matters: the same company scores differently for different
    campaigns, which is the point of scoring per campaign rather than per
    contact.
    """
    known = _contact_words(contact)
    reasons: list[str] = []
    risks: list[str] = []

    # ---- ICP fit: what the sender says their best customer looks like
    icp = _words(profile.get("ideal_customer_profile") or "")
    icp_hit = _affinity(known, icp, saturate=3)
    icp_points = round(40 * icp_hit)
    if icp_points >= 16:
        reasons.append("matches-icp")
    elif icp:
        risks.append("icp-unclear")

    # ---- offer match: is the thing we are selling relevant to them
    offer_words: set[str] = set()
    if offer:
        offer_words = _words(f"{offer.get('name', '')} {offer.get('description', '')}")
    offer_hit = _affinity(known, offer_words, saturate=2)
    offer_points = round(30 * offer_hit)
    if offer_points >= 12:
        reasons.append("offer-relevant")
    elif offer_words:
        # A forced offer that does not fit must visibly lower the score
        # rather than quietly scoring the same as a relevant one (§16.7).
        risks.append("offer-mismatch")

    # ---- industry: what the finder recorded them as
    industry_words = _words(" ".join(
        str(p) for p in (profile.get("customer_pain_points") or [])
        + (profile.get("differentiators") or [])))
    industry_points = round(15 * _affinity(known, industry_words, saturate=2))
    if industry_points >= 6:
        reasons.append("industry-fit")

    # ---- location: three outcomes, not two
    #
    # "in the target market", "somewhere else" and "we do not know" are
    # different answers, and only the middle one is a reason not to write.
    # Treating the third as the second is how a prospect we simply have no
    # country for ends up looking like a bad fit.
    place = _place_words(contact)
    if not region.strip():
        location_points = 15            # no geography asked for
    elif not place:
        location_points = 8             # unknown: neutral, and said so
        risks.append("location-unknown")
    elif _affinity(place, _words(region), saturate=1):
        location_points = 15
        reasons.append("in-target-market")
    else:
        location_points = 0
        risks.append("outside-target-market")

    # ---- can we write something specific to them at all
    #
    # Reported BESIDE the score, never inside it. Whether we can open with
    # a verified observation is a readiness question; whether they want
    # what the sender sells is a fit question. A business with no website
    # may be a perfect customer we happen to know little about, and
    # deducting for that would bury exactly the small businesses this
    # product is sold to.
    ready = bool(str(contact.get("website") or "").strip())
    if not ready:
        risks.append("no-website")

    score = int(max(0, min(100, icp_points + offer_points
                           + industry_points + location_points)))

    confidence = confidence_for(contact)
    if confidence < 0.4:
        # A RISK, not a deduction. Saying "we do not know much about this
        # one" is useful; subtracting for it would mean a perfect match we
        # happen not to have read about ranks below a poor one we have.
        risks.append("little-known")

    return {
        "score": score,
        "band": band_for(score),
        "research_confidence": confidence,
        "best_offer": (offer or {}).get("name", ""),
        # Separate from fit on purpose (§16.2): can we write something
        # specific, as opposed to do they want it.
        "personalization_ready": ready,
        "reasons": reasons,
        "risks": risks,
        "score_version": SCORE_VERSION,
    }


def best_offer(contact: dict, profile: dict) -> dict | None:
    """Which of the sender's offers fits this prospect best.

    Used when the campaign lets MailPilot choose (§16.7). With one offer
    this is trivially that offer; with none it is None and offer match
    simply does not contribute.
    """
    offers = profile.get("offers") or []
    if not offers:
        return None
    known = _contact_words(contact)
    return max(
        offers,
        key=lambda o: _affinity(known, _words(f"{o.get('name','')} {o.get('description','')}"), saturate=2),
    )


def score_campaign(campaign_id: str, contacts: list[dict], *, profile: dict,
                   forced_offer: dict | None = None, region: str = "") -> list[dict]:
    """Score everyone selected for a campaign, and remember the result.

    Stored rather than recomputed on every render so the pre-flight figures
    and the send order cannot disagree, and so §16.9's "latest score plus a
    send-time snapshot" has somewhere to live.
    """
    out = []
    now = iso()
    with db.transaction():
        for contact in contacts:
            offer = forced_offer or best_offer(contact, profile)
            verdict = score_for(contact, profile=profile, offer=offer, region=region)
            verdict["contact_id"] = contact.get("id") or ""
            verdict["email"] = contact.get("email") or ""
            out.append(verdict)

            existing = db.one(
                "SELECT id FROM prospect_scores WHERE campaign_id = ? AND contact_id = ?",
                (campaign_id, verdict["contact_id"]))
            row = {
                "campaign_id": campaign_id,
                "contact_id": verdict["contact_id"],
                "score": verdict["score"],
                "band": verdict["band"],
                "confidence": verdict["research_confidence"],
                "best_offer": verdict["best_offer"],
                "reasons": db.dumps(verdict["reasons"]),
                "risks": db.dumps(verdict["risks"]),
                "score_version": SCORE_VERSION,
                "created_at": now,
            }
            if existing:
                db.update("prospect_scores", existing["id"], row)
            else:
                db.insert("prospect_scores", {"id": new_id("ps"), **row})
    return out


def distribution(scored: list[dict]) -> dict[str, int]:
    """How many fall in each band, for the pre-flight summary."""
    out = {name: 0 for _, name in BANDS}
    for s in scored:
        out[s["band"]] = out.get(s["band"], 0) + 1
    return out


def snapshot_at_send(campaign_id: str, contact_id: str) -> None:
    """Freeze the score as it was when the message went out.

    The live score may move afterwards as research improves. History must
    not: "why did we mail this one?" has to be answerable with the number
    that was true at the time, not the number that is true now (§16.9).
    """
    row = db.one(
        "SELECT * FROM prospect_scores WHERE campaign_id = ? AND contact_id = ?",
        (campaign_id, contact_id))
    if row is None or row["sent_snapshot"]:
        return
    db.update("prospect_scores", row["id"], {
        "sent_snapshot": db.dumps({
            "score": row["score"], "band": row["band"],
            "confidence": row["confidence"],
            "score_version": row["score_version"], "at": iso(),
        }),
    })
