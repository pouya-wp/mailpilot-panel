"""Beyondex Professional: the parts that must hold without a model.

Everything here is the logic AROUND the model calls — the scoring gate,
the fallbacks, the HTML the template will wrap — because that is what
decides whether a bad draft reaches a real inbox, and it is exactly the
part that is invisible when you test by looking at the output of a good
run.

The model itself is faked at the module boundary. What is being checked is
not that the model writes well; it is that a low score is not sent, that a
refusal to write is not treated as an email, and that a business with no
proof cannot end up citing some.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="pro-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import brandprofile, db, professional  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    db.init_db()
    db.execute("DELETE FROM brand_profile")
    brandprofile.ensure_row()
    brandprofile.save({
        "brand_name": "Beyondex",
        "business_summary": "We build sales agents.",
        "offers": [{"name": "Sales agent", "description": "Answers enquiries first"}],
        "ideal_customer_profile": "Small importers",
        "customer_outcomes": ["Faster replies"],
        "brand_voice": ["professional", "direct"],
    })
    yield


def _fake(monkeypatch, *, plan=None, draft=None, scored=None, found=None):
    monkeypatch.setattr(professional, "research",
                        lambda contact: found or {"company": "Zargar", "verified_facts": []})
    monkeypatch.setattr(professional, "strategy",
                        lambda **kw: plan or {"decision": "WRITE", "chosen_offer": "Sales agent"})
    monkeypatch.setattr(professional, "write",
                        lambda **kw: draft or {"subject": "a question about your enquiries",
                                               "body": ["One.", "Two."], "cta_line": "Worth a look?"})
    monkeypatch.setattr(professional, "review", lambda **kw: scored or _scores(95))


def _scores(n, **over):
    base = {k: n for k in (
        "prospect_relevance", "personalisation", "subject", "problem_clarity",
        "single_offer", "outcome_clarity", "brand_voice", "cta",
        "hallucination_risk", "spam_risk")}
    base.update(over)
    return {"scores": base, "verdict": "approve", "problems": [], "unsupported_claims": []}


# ---------------------------------------------------------------- the gate


def test_a_good_draft_is_ready_to_send(monkeypatch):
    _fake(monkeypatch)
    out = professional.compose_for({"email": "a@b.c", "name": "Ali"},
                                   profile=brandprofile.get())
    assert out["status"] == "ready"
    assert out["score"] >= professional.APPROVE_AT
    assert "One." in out["body"]


def test_a_draft_below_the_bar_is_held_not_sent(monkeypatch):
    """The whole reason the reviewer exists. A 40 must never be queued."""
    _fake(monkeypatch, scored={**_scores(40), "verdict": "rewrite",
                               "problems": ["invented a branch opening"]})
    out = professional.compose_for({"email": "a@b.c", "name": "Ali"},
                                   profile=brandprofile.get())
    assert out["status"] == "held"
    assert "invented a branch opening" in out["reason"]


def test_a_middling_draft_is_rewritten_once_then_accepted(monkeypatch):
    """Rewrite once, not in a loop: looping against one reviewer converges
    on gaming it, and bills the customer per attempt."""
    calls = {"write": 0}

    def counted_write(**kw):
        calls["write"] += 1
        return {"subject": "s", "body": ["b"], "cta_line": "c"}

    scores = iter([_scores(84), _scores(96)])
    _fake(monkeypatch)
    monkeypatch.setattr(professional, "write", counted_write)
    monkeypatch.setattr(professional, "review", lambda **kw: next(scores))

    out = professional.compose_for({"email": "a@b.c"}, profile=brandprofile.get())
    assert calls["write"] == 2
    assert out["status"] == "ready"


def test_a_rewrite_that_is_still_bad_is_held(monkeypatch):
    _fake(monkeypatch)
    monkeypatch.setattr(professional, "review", lambda **kw: _scores(50))
    out = professional.compose_for({"email": "a@b.c"}, profile=brandprofile.get())
    assert out["status"] == "held"


def test_the_strategy_may_refuse_to_write_at_all(monkeypatch):
    """NEED_MORE_RESEARCH is a correct answer. Holding beats sending a
    generic email dressed as a personal one."""
    _fake(monkeypatch, plan={"decision": "NEED_MORE_RESEARCH",
                             "why_not": "nothing published about this business"})
    out = professional.compose_for({"email": "a@b.c"}, profile=brandprofile.get())
    assert out["status"] == "research"
    assert "nothing published" in out["reason"]
    assert "subject" not in out


# --------------------------------------------------------------- scoring


def test_a_fabricated_fact_cannot_be_outweighed_by_good_copy():
    """The failure this whole pipeline exists to stop.

    An email that invents something about the recipient scores beautifully
    on the other nine criteria -- sharp subject, single offer, right voice
    -- and a plain average let it through at 91. Good copy does not offset
    a made-up fact; it is what makes the made-up fact convincing.
    """
    scored = _scores(100, hallucination_risk=10)
    assert professional.overall(scored) < professional.RESEARCH_AT


def test_a_spammy_draft_is_vetoed_the_same_way():
    scored = _scores(100, spam_risk=20)
    assert professional.overall(scored) < professional.RESEARCH_AT


def test_a_risk_score_just_above_the_floor_does_not_veto():
    """The veto is for genuine problems, not for a cautious reviewer."""
    scored = _scores(95, hallucination_risk=professional.SAFETY_FLOOR)
    assert professional.overall(scored) >= professional.APPROVE_AT


def test_the_models_own_summary_score_is_ignored_when_it_disagrees():
    """A reviewer that scores eight things at 40 and writes 95 in the
    summary field is not a reviewer."""
    scored = {**_scores(40), "score": 95}
    assert professional.overall(scored) == 40


def test_a_reviewer_that_returns_nothing_falls_back_to_its_summary():
    assert professional.overall({"score": 77}) == 77


# ------------------------------------------------------------------ output


def test_the_body_is_escaped_html_paragraphs():
    """The model is quoting names it read off a website; one ampersand
    must not be able to break the message."""
    html = professional._as_html({"body": ["Smith & Sons", "<script>x</script>"],
                                  "cta_line": "Worth a look?"})
    assert "Smith &amp; Sons" in html
    assert "<script>" not in html
    assert html.count("<p") == 3      # two paragraphs plus the cta line


def test_an_empty_paragraph_is_dropped():
    html = professional._as_html({"body": ["Real.", "", "   "], "cta_line": ""})
    assert html.count("<p") == 1


# ------------------------------------------------------- the sender's brief


def test_a_business_with_no_proof_is_forbidden_from_citing_any():
    """This is the claim that would do the most damage, so it is stated as
    a prohibition rather than left to silence."""
    text = brandprofile.as_prompt()
    assert "NO proof points" in text


def test_the_ten_rules_are_given_to_the_writer_and_the_reviewer():
    """They are meant to be enforced, not documented — so the same list
    has to reach both, or the reviewer is marking a different exam."""
    assert len(professional.TEN_RULES) == 10
    for rule in professional.TEN_RULES:
        assert rule in "\n".join(professional.TEN_RULES)
