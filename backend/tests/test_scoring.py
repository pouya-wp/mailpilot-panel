"""Prospect fit.

The three scenarios the brief names are all about NOT over-claiming:

  * a relevant prospect must outrank an irrelevant one, and the rationale
    must cite only business facts;
  * a prospect we know little about must not be forced to a low FIT score
    merely for being obscure — confidence is a separate number;
  * a suppressed contact with a perfect score must still be unsendable.

The last one is the important one architecturally: scoring must not be
able to grant permission, and nothing in this module can.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="score-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import db, eligibility, scoring  # noqa: E402
from app.domain import iso  # noqa: E402
from app.security import new_id  # noqa: E402

PROFILE = {
    "ideal_customer_profile":
        "independent jewellery retailers and gold shops selling to walk-in customers",
    "offers": [{"name": "Sales agent",
                "description": "answers customer enquiries about jewellery stock and pricing"}],
    "customer_pain_points": ["slow replies to customer enquiries"],
    "differentiators": ["fast replies"],
}
OFFER = PROFILE["offers"][0]

IDEAL = {"id": "c1", "email": "a@zargar.ae", "company": "Zargar Gold Jewellery",
         "website": "https://zargar.ae", "country": "AE",
         "tags": '["gold shops Dubai"]', "source_en": "Research: zargar.ae"}
IRRELEVANT = {"id": "c2", "email": "b@tractor.example", "company": "Heavy Tractor Parts",
              "website": "https://tractor.example", "country": "DE",
              "tags": '["farm machinery Berlin"]', "source_en": ""}
THIN = {"id": "c3", "email": "c@x.ae", "company": "Gold Jewellery Shop",
        "website": "", "country": "", "tags": "[]", "source_en": ""}


@pytest.fixture(autouse=True)
def _fresh():
    db.init_db()
    for table in ("prospect_scores", "suppression", "contacts"):
        db.execute(f"DELETE FROM {table}")
    yield


def _score(contact, region="Dubai"):
    return scoring.score_for(contact, profile=PROFILE, offer=OFFER, region=region)


# ------------------------------------------------------------- the ranking


def test_a_relevant_prospect_outranks_an_irrelevant_one():
    """The brief's scenario 6."""
    assert _score(IDEAL)["score"] > _score(IRRELEVANT)["score"]
    assert _score(IDEAL)["band"] in {"HIGH_FIT", "GOOD_FIT"}
    assert _score(IRRELEVANT)["band"] == "LOW_FIT"


def test_the_rationale_cites_only_business_factors():
    """Reasons are a fixed vocabulary of business facts, not model prose --
    so there is no path by which a sensitive attribute could appear in
    one."""
    allowed = {"matches-icp", "offer-relevant", "industry-fit", "in-target-market"}
    assert set(_score(IDEAL)["reasons"]) <= allowed


# --------------------------------------------------- obscurity is not unfit


def test_a_sparse_prospect_that_matches_is_not_forced_low():
    """The brief's scenario 7, and §16.2.

    Knowing little about a business is a reason to look it up, not a
    reason to decide it is a poor customer. Scoring them low would
    systematically bury the small businesses this product is sold to.
    """
    thin = _score(THIN)
    assert thin["research_confidence"] < 0.4
    assert thin["band"] != "LOW_FIT"
    assert "matches-icp" in thin["reasons"]


def test_confidence_and_fit_are_different_numbers():
    """The ideal prospect and the thin one both match; only one is known."""
    assert _score(IDEAL)["research_confidence"] > _score(THIN)["research_confidence"]
    assert _score(THIN)["score"] > _score(IRRELEVANT)["score"]


def test_a_missing_website_is_a_risk_not_a_deduction():
    """Readiness to personalise is reported beside the score, never in it."""
    with_site = dict(THIN, website="https://goldshop.example")
    assert _score(with_site)["score"] == _score(THIN)["score"]
    assert _score(THIN)["personalization_ready"] is False
    assert "no-website" in _score(THIN)["risks"]


def test_an_unknown_location_is_not_the_wrong_location():
    """"We do not know where they are" and "they are elsewhere" are
    different facts, and only one is a reason not to write."""
    unknown = _score(THIN)
    elsewhere = _score(IRRELEVANT)
    assert "location-unknown" in unknown["risks"]
    assert "outside-target-market" in elsewhere["risks"]
    assert "outside-target-market" not in unknown["risks"]


# ------------------------------------------------------- the offer matters


def test_the_same_company_scores_differently_for_a_different_offer():
    """Which is the whole reason scoring is per campaign, not per contact."""
    unrelated = {"name": "Tractor parts logistics",
                 "description": "heavy machinery spare part delivery"}
    relevant = scoring.score_for(IDEAL, profile=PROFILE, offer=OFFER, region="Dubai")
    forced = scoring.score_for(IDEAL, profile=PROFILE, offer=unrelated, region="Dubai")
    assert forced["score"] < relevant["score"]
    assert "offer-mismatch" in forced["risks"]


def test_the_best_offer_is_the_one_that_actually_matches():
    profile = dict(PROFILE, offers=[
        {"name": "Tractor parts", "description": "heavy machinery spares"},
        {"name": "Jewellery sales agent", "description": "answers gold and jewellery enquiries"},
    ])
    assert scoring.best_offer(IDEAL, profile)["name"] == "Jewellery sales agent"


# ------------------------------------------------ a score is not permission


def test_a_perfect_score_does_not_make_a_suppressed_contact_sendable():
    """The brief's scenario 8, and the one property that must not break.

    Scoring and eligibility are separate modules on purpose: nothing in
    scoring can reach the decision about whether a message may go out.
    """
    db.insert("suppression", {"id": new_id("sup"), "email": "a@zargar.ae",
                              "reason": "unsub", "created_at": iso()})

    assert _score(IDEAL)["score"] > 50          # a good prospect by fit
    verdict = eligibility.classify("c-x", [{"email": "a@zargar.ae"}])
    assert verdict["eligibleCount"] == 0        # and still not sendable
    assert eligibility.may_send_now("a@zargar.ae") == "suppressed"


def test_scoring_cannot_write_to_suppression_or_outbox():
    """A guard against a future shortcut. If someone ever makes scoring
    'helpfully' drop low-fit contacts, this is where it is noticed."""
    source = (Path(__file__).resolve().parents[1] / "app" / "scoring.py").read_text(encoding="utf-8")
    for table in ("suppression", "outbox", "contacts"):
        assert f'INSERT INTO {table}' not in source
        assert f'db.insert("{table}"' not in source


# ----------------------------------------------------------- bookkeeping


def test_bands_follow_the_specified_thresholds():
    assert scoring.band_for(100) == "HIGH_FIT"
    assert scoring.band_for(85) == "HIGH_FIT"
    assert scoring.band_for(84) == "GOOD_FIT"
    assert scoring.band_for(70) == "GOOD_FIT"
    assert scoring.band_for(69) == "MEDIUM_FIT"
    assert scoring.band_for(50) == "MEDIUM_FIT"
    assert scoring.band_for(49) == "LOW_FIT"
    assert scoring.band_for(0) == "LOW_FIT"


def test_low_fit_is_not_included_by_default():
    """§16.6 — excluded unless the customer says otherwise."""
    assert "LOW_FIT" not in scoring.DEFAULT_INCLUDED
    assert "MEDIUM_FIT" not in scoring.DEFAULT_INCLUDED
    assert scoring.DEFAULT_INCLUDED == {"HIGH_FIT", "GOOD_FIT"}


def test_a_score_carries_its_version():
    """So an old score stays interpretable beside a new one rather than
    being silently compared across a change in meaning."""
    assert _score(IDEAL)["score_version"] == scoring.SCORE_VERSION


def test_scoring_a_campaign_stores_one_row_per_contact_and_is_idempotent():
    contacts = [IDEAL, IRRELEVANT, THIN]
    scoring.score_campaign("c-1", contacts, profile=PROFILE, region="Dubai")
    scoring.score_campaign("c-1", contacts, profile=PROFILE, region="Dubai")
    assert db.scalar("SELECT COUNT(*) FROM prospect_scores WHERE campaign_id='c-1'",
                     default=0) == 3


def test_the_send_time_score_is_frozen():
    """§16.9 — the live score may move as research improves; history must
    not, or "why did we mail this one?" becomes unanswerable."""
    scoring.score_campaign("c-2", [IDEAL], profile=PROFILE, region="Dubai")
    scoring.snapshot_at_send("c-2", "c1")
    first = db.one("SELECT sent_snapshot FROM prospect_scores WHERE campaign_id='c-2'")["sent_snapshot"]
    assert first

    # re-scoring afterwards must not rewrite the snapshot
    db.execute("UPDATE prospect_scores SET score = 12 WHERE campaign_id='c-2'")
    scoring.snapshot_at_send("c-2", "c1")
    again = db.one("SELECT sent_snapshot FROM prospect_scores WHERE campaign_id='c-2'")["sent_snapshot"]
    assert again == first


def test_the_distribution_counts_every_band():
    scored = [_score(IDEAL), _score(IRRELEVANT), _score(THIN)]
    dist = scoring.distribution(scored)
    assert sum(dist.values()) == 3
    assert set(dist) == {"HIGH_FIT", "GOOD_FIT", "MEDIUM_FIT", "LOW_FIT"}


# ------------------------------------------------- fit orders, never admits


def test_better_fit_prospects_are_queued_first():
    """Fit decides who goes FIRST. The sender drains oldest-first with rowid
    as the tie-break, so writing the rows in fit order is what makes the
    better prospects go out at the front of a paced campaign."""
    from app import brandprofile, mailer

    brandprofile.save({
        "ideal_customer_profile": PROFILE["ideal_customer_profile"],
        "offers": PROFILE["offers"],
    })
    db.execute("DELETE FROM outbox")

    # deliberately supplied worst-first
    mailer.enqueue("c-order", recipients=[
        dict(IRRELEVANT, id="c2"), dict(THIN, id="c3"), dict(IDEAL, id="c1"),
    ])
    order = [r["email"] for r in db.query(
        "SELECT email FROM outbox WHERE campaign_id='c-order' AND status='queued' "
        "ORDER BY queued_at, rowid")]
    assert order[0] == IDEAL["email"], f"best fit should lead, got {order}"


def test_fit_ordering_never_widens_who_is_sent_to():
    """Scenario 8 again, at the queue rather than the classifier: a
    suppressed contact with a strong score is still not queued."""
    from app import brandprofile, mailer

    brandprofile.save({
        "ideal_customer_profile": PROFILE["ideal_customer_profile"],
        "offers": PROFILE["offers"],
    })
    db.execute("DELETE FROM outbox")
    db.insert("suppression", {"id": new_id("sup"), "email": IDEAL["email"],
                              "reason": "unsub", "created_at": iso()})

    queued = mailer.enqueue("c-block", recipients=[dict(IDEAL, id="c1")])
    assert queued == 0
    row = db.one("SELECT status, error FROM outbox WHERE campaign_id='c-block'")
    assert row["status"] == "blocked"
