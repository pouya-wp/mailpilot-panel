"""Learning which emails work, without pretending to know too early.

The dangerous version of this feature is the easy one: compare two rates,
call the bigger one the winner, print a percentage. With twenty recipients
per arm that is astrology, and because it arrives with a number beside it
the customer believes it and changes their copy to match noise.

So three rules shape everything here.

REPLIES BEAT OPENS. An open is a pixel that Apple Mail Privacy Protection
fires whether or not a human looked, and every mailbox provider is making
it worse. A reply is a person typing. Opens are reported because customers
expect them and are never what a winner is chosen on.

A WINNER NEEDS EVIDENCE, NOT JUST A LEAD. Both arms must reach a minimum
sample, and their confidence intervals must actually separate. Otherwise
the answer is INCONCLUSIVE, which is a real result and is shown as one.

THE COST SIDE COUNTS. A variant that gets more replies and twice the
unsubscribes is not a winner. The score subtracts the harm.

THE METHOD, STATED ONCE. Proportions are compared with the Wilson score
interval at 95%. Wilson rather than the normal approximation because the
normal one is badly wrong exactly where this lives — small samples and
rates near zero, where it happily produces a negative lower bound for a
reply rate. It is closed-form, so there is no dependency, and the same
function is used for every rate on this screen so two numbers can never be
computed two ways.
"""

from __future__ import annotations

import math
import random
from typing import Any

from . import db
from .domain import iso
from .security import new_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_variants (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  label       TEXT NOT NULL,
  field       TEXT NOT NULL DEFAULT 'subject',
  value       TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_variants_campaign ON campaign_variants(campaign_id);

CREATE TABLE IF NOT EXISTS learnings (
  id                  TEXT PRIMARY KEY,
  segment_key         TEXT NOT NULL DEFAULT '',
  offer               TEXT NOT NULL DEFAULT '',
  subject_pattern     TEXT NOT NULL DEFAULT '',
  cta_type            TEXT NOT NULL DEFAULT '',
  email_angle         TEXT NOT NULL DEFAULT '',
  sample_size         INTEGER NOT NULL DEFAULT 0,
  reply_rate          REAL NOT NULL DEFAULT 0,
  positive_reply_rate REAL NOT NULL DEFAULT 0,
  unsubscribe_rate    REAL NOT NULL DEFAULT 0,
  confidence          REAL NOT NULL DEFAULT 0,
  campaigns           TEXT NOT NULL DEFAULT '[]',
  last_updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_learnings_segment ON learnings(segment_key);
"""

#: Which single thing an A/B test varies. One at a time on purpose: a test
#: that changes the subject AND the call to action cannot tell you which of
#: them moved the number, so it teaches nothing while costing a campaign.
FIELDS = ("subject", "cta", "angle")

#: Defaults, overridable per deployment for the same reason the sender
#: health thresholds are: there is no universal right answer, and a number
#: hard-coded here would be presented to customers as if there were.
DEFAULTS = {
    # per arm, before a winner may be declared at all
    "min_sample": 100,
    # a reply rate this far apart, with intervals that do not overlap
    "confidence": 0.95,
    # how much an unsubscribe costs against a reply, in the score
    "unsub_weight": 3.0,
    "bounce_weight": 2.0,
    # a positive reply is worth more than a bare reply
    "positive_weight": 2.0,
}


def limits() -> dict[str, float]:
    from . import deployment

    out = dict(DEFAULTS)
    try:
        raw = deployment.get().get("optimize_settings") or "{}"
        for key, value in (db.loads(raw, {}) or {}).items():
            if key in out:
                out[key] = float(value)
    except (ValueError, TypeError, AttributeError):
        pass
    return out


# =============================================================== statistics


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """A 95% confidence interval for a proportion.

    Wilson rather than the normal approximation, which is wrong in exactly
    the conditions this feature lives in: small samples and rates close to
    zero, where it cheerfully returns a negative lower bound for a reply
    rate. Closed-form, so no dependency.
    """
    if trials <= 0:
        return (0.0, 0.0)
    p = successes / trials
    denom = 1 + z * z / trials
    centre = p + z * z / (2 * trials)
    spread = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials))
    return (max(0.0, (centre - spread) / denom), min(1.0, (centre + spread) / denom))


def rate(successes: int, trials: int) -> float | None:
    """None when there is nothing to divide by.

    Not 0.0: "nobody replied to a thousand emails" and "we have not sent
    any" are opposite facts and a caller that cannot tell them apart draws
    a zero bar for both.
    """
    return round(successes / trials, 4) if trials else None


# ================================================================== the arms


def arm(campaign_id: str, variant: str = "") -> dict[str, Any]:
    """What actually happened to one arm of a campaign.

    Counted from the outbox and the events it produced, keyed on the
    variant the recipient was assigned — so a campaign with no A/B test
    still works, with everything in one unnamed arm.
    """
    where = "campaign_id = ?"
    params: list[Any] = [campaign_id]
    if variant:
        where += " AND variant = ?"
        params.append(variant)

    sent = db.scalar(
        f"SELECT COUNT(*) FROM outbox WHERE {where} AND status = 'sent'",
        params, default=0) or 0
    emails = [
        (r["email"] or "").lower()
        for r in db.query(f"SELECT email FROM outbox WHERE {where} AND status = 'sent'", params)
    ]

    replies = positives = questions = 0
    if emails:
        marks = ", ".join("?" for _ in emails)
        rows = db.query(
            f"SELECT intent, COUNT(*) n FROM threads "
            f"WHERE lower(email) IN ({marks}) GROUP BY intent", emails)
        for r in rows:
            intent = r["intent"] or ""
            # An out-of-office is a mail server, not a person, and counting
            # it as engagement is how a badly-timed campaign looks like a
            # successful one. An opt-out is a reply and is emphatically not
            # a positive one.
            if intent == "ooo":
                continue
            replies += r["n"]
            if intent == "interested":
                positives += r["n"]
            elif intent == "question":
                questions += r["n"]

    unsubs = bounces = 0
    if emails:
        marks = ", ".join("?" for _ in emails)
        unsubs = db.scalar(
            f"SELECT COUNT(*) FROM suppression WHERE reason = 'unsub' "
            f"AND lower(email) IN ({marks})", emails, default=0) or 0
        bounces = db.scalar(
            f"SELECT COUNT(*) FROM suppression WHERE reason = 'bounce' "
            f"AND lower(email) IN ({marks})", emails, default=0) or 0

    low, high = wilson(positives, sent)
    return {
        "variant": variant or "-",
        "sent": sent,
        "replies": replies,
        "positives": positives,
        "questions": questions,
        "unsubscribes": unsubs,
        "bounces": bounces,
        "replyRate": rate(replies, sent),
        "positiveReplyRate": rate(positives, sent),
        "questionRate": rate(questions, sent),
        "unsubscribeRate": rate(unsubs, sent),
        "bounceRate": rate(bounces, sent),
        # the interval the winner decision is actually made on
        "positiveLow": round(low, 4),
        "positiveHigh": round(high, 4),
    }


def score(a: dict[str, Any], weights: dict[str, float]) -> float:
    """One number, with the harm subtracted.

    A variant that wins more replies and twice the unsubscribes has not
    won. Rates rather than counts, so unequal arms compare honestly.
    """
    if not a["sent"]:
        return 0.0
    return round(
        (a["positiveReplyRate"] or 0) * weights["positive_weight"]
        + (a["replyRate"] or 0)
        - (a["unsubscribeRate"] or 0) * weights["unsub_weight"]
        - (a["bounceRate"] or 0) * weights["bounce_weight"],
        6,
    )


# ================================================================ the winner


def decide(campaign_id: str) -> dict[str, Any]:
    """Which arm won, or that we do not yet know.

    INCONCLUSIVE is a real answer and the most common honest one. It is
    returned whenever either arm is under the sample floor or the intervals
    still overlap — a lead is not a result.
    """
    weights = limits()
    variants = db.query(
        "SELECT * FROM campaign_variants WHERE campaign_id = ? ORDER BY label",
        (campaign_id,))
    if len(variants) < 2:
        return {"result": "NO_TEST", "arms": []}

    arms = [arm(campaign_id, v["label"]) for v in variants]
    for a, v in zip(arms, variants):
        a["field"] = v["field"]
        a["value"] = v["value"]
        a["score"] = score(a, weights)

    floor = int(weights["min_sample"])
    thin = [a for a in arms if a["sent"] < floor]
    if thin:
        return {
            "result": "INCONCLUSIVE",
            "reason": "sample",
            "needed": floor,
            "arms": arms,
        }

    ranked = sorted(arms, key=lambda a: a["score"], reverse=True)
    best, second = ranked[0], ranked[1]

    # The intervals must actually separate. Two rates being different is
    # not evidence that they are different, and this is the line between a
    # finding and a coincidence.
    if best["positiveLow"] <= second["positiveHigh"]:
        return {
            "result": "INCONCLUSIVE",
            "reason": "overlap",
            "arms": arms,
        }

    return {
        "result": best["variant"],
        "reason": "separated",
        "winner": best,
        "arms": arms,
        # A number the evidence actually supports: how far apart the
        # intervals are, not a made-up precision.
        "confidence": round(min(0.99, best["positiveLow"] - second["positiveHigh"] + 0.95), 2),
    }


# ============================================================== assignment


def assign(campaign_id: str, recipients: list[dict]) -> dict[str, str]:
    """Split recipients between the arms, once and for good.

    Stored on the outbox row, so a recipient can never receive a second
    first-touch variant — re-running this for a campaign that is already
    assigned returns what was decided the first time rather than
    reshuffling people who have already been written to.
    """
    variants = db.query(
        "SELECT label FROM campaign_variants WHERE campaign_id = ? ORDER BY label",
        (campaign_id,))
    if len(variants) < 2:
        return {}

    labels = [v["label"] for v in variants]
    existing = {
        (r["email"] or "").lower(): r["variant"]
        for r in db.query(
            "SELECT email, variant FROM outbox WHERE campaign_id = ? AND variant != ''",
            (campaign_id,))
    }

    # Seeded on the campaign so the split is reproducible: the same campaign
    # assigned twice produces the same answer, which makes this testable and
    # makes a re-queue after a crash land people where they already were.
    rng = random.Random(f"{campaign_id}:ab")
    out: dict[str, str] = {}
    pool: list[str] = []
    for person in recipients:
        email = (person.get("email") or "").strip().lower()
        if not email:
            continue
        if email in existing:
            out[email] = existing[email]
            continue
        if not pool:
            # deal from a shuffled pack rather than choosing per person, so
            # the arms stay even instead of merely even in expectation
            pool = labels * 4
            rng.shuffle(pool)
        out[email] = pool.pop()
    return out


def allocation(campaign_id: str, total: int) -> list[dict[str, Any]]:
    """What the split will look like, for the screen before launch."""
    variants = db.query(
        "SELECT * FROM campaign_variants WHERE campaign_id = ? ORDER BY label",
        (campaign_id,))
    if len(variants) < 2:
        return []
    each = total // len(variants)
    out = []
    for i, v in enumerate(variants):
        n = each + (total - each * len(variants) if i == 0 else 0)
        out.append({"label": v["label"], "field": v["field"],
                    "value": v["value"], "recipients": n})
    return out


def set_variants(campaign_id: str, field: str, values: list[str]) -> list[dict]:
    """Define the test. One field, two or more values."""
    if field not in FIELDS:
        raise ValueError(f"not a testable field: {field}")
    clean = [v.strip() for v in values if v.strip()][:4]
    if len(clean) < 2:
        raise ValueError("a test needs at least two variants")

    with db.transaction():
        db.execute("DELETE FROM campaign_variants WHERE campaign_id = ?", (campaign_id,))
        for label, value in zip("ABCD", clean):
            db.insert("campaign_variants", {
                "id": new_id("var"), "campaign_id": campaign_id,
                "label": label, "field": field, "value": value,
                "created_at": iso(),
            })
    return db.query("SELECT * FROM campaign_variants WHERE campaign_id = ? ORDER BY label",
                    (campaign_id,))


# ================================================================ learning

def _segment_key(campaign_id: str) -> str:
    """A coarse label for "what kind of campaign was this".

    Coarse on purpose. A key that is too specific matches nothing and the
    learning loop never fires; one that is too loose matches everything and
    recommends Dubai jewellers' copy to a Berlin dentist. The group's own
    name is the best signal this product has, because the finder names
    groups after the search that produced them ("gold shops Dubai").
    """
    row = db.one("SELECT segment_id FROM campaigns WHERE id = ?", (campaign_id,))
    if row is None or not row["segment_id"]:
        return ""
    seg = db.one("SELECT name_en FROM segments WHERE id = ?", (row["segment_id"],))
    return (seg["name_en"] if seg else "").strip().lower()


def learn_from(campaign_id: str) -> dict[str, Any] | None:
    """Fold one finished campaign into the learning records.

    Written per (segment, cta) rather than per campaign, so three similar
    campaigns accumulate into one record with a sample worth reading rather
    than three records nobody can act on.

    Returns None when there is nothing worth learning: no segment to key
    on, or nothing actually sent.
    """
    key = _segment_key(campaign_id)
    stats = arm(campaign_id)
    if not key or not stats["sent"]:
        return None

    from . import brandprofile

    cta = (brandprofile.get().get("preferred_cta") or "").strip()
    existing = db.one(
        "SELECT * FROM learnings WHERE segment_key = ? AND cta_type = ?", (key, cta))

    campaigns = db.loads(existing["campaigns"], []) if existing else []
    if campaign_id in campaigns:
        return None                      # already folded in
    campaigns.append(campaign_id)

    # Pooled totals, not an average of rates: averaging a 2-recipient
    # campaign with a 2,000-recipient one gives the small one half the vote.
    sent = replies = positives = unsubs = 0
    for cid in campaigns:
        s = arm(cid)
        sent += s["sent"]
        replies += s["replies"]
        positives += s["positives"]
        unsubs += s["unsubscribes"]

    low, high = wilson(positives, sent)
    record = {
        "segment_key": key,
        "offer": "",
        "subject_pattern": "",
        "cta_type": cta,
        "email_angle": "",
        "sample_size": sent,
        "reply_rate": rate(replies, sent) or 0,
        "positive_reply_rate": rate(positives, sent) or 0,
        "unsubscribe_rate": rate(unsubs, sent) or 0,
        # How much the evidence narrows the answer. A wide interval is a
        # low number, which is exactly what "we are not sure" should look
        # like when it reaches the screen.
        "confidence": round(max(0.0, 1 - (high - low)), 2),
        "campaigns": db.dumps(campaigns),
        "last_updated_at": iso(),
    }

    with db.transaction():
        if existing:
            db.update("learnings", existing["id"], record)
        else:
            db.insert("learnings", {"id": new_id("lrn"), **record})
    return record


def recommend(segment_id: str | None) -> dict[str, Any] | None:
    """What past campaigns to a similar audience suggest, if anything.

    A SUGGESTION. Nothing here is applied; the caller shows it and the
    customer decides. Returns None rather than a weak recommendation,
    because a recommendation with no evidence behind it is worse than
    silence — it gets followed.
    """
    if not segment_id:
        return None
    seg = db.one("SELECT name_en FROM segments WHERE id = ?", (segment_id,))
    if seg is None:
        return None
    key = (seg["name_en"] or "").strip().lower()

    row = db.one(
        "SELECT * FROM learnings WHERE segment_key = ? ORDER BY sample_size DESC", (key,))
    if row is None:
        return None

    floor = int(limits()["min_sample"])
    if row["sample_size"] < floor:
        # Not silence: the screen says "not enough data yet", which is true
        # and stops the customer wondering whether the feature is broken.
        return {
            "enough": False,
            "sampleSize": row["sample_size"],
            "needed": floor,
            "segment": seg["name_en"],
        }

    return {
        "enough": True,
        "segment": seg["name_en"],
        "ctaType": row["cta_type"],
        "sampleSize": row["sample_size"],
        "replyRate": row["reply_rate"],
        "positiveReplyRate": row["positive_reply_rate"],
        "unsubscribeRate": row["unsubscribe_rate"],
        "confidence": row["confidence"],
        "campaigns": db.loads(row["campaigns"], []),
    }
