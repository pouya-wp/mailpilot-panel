"""The Brand Information profile.

The two behaviours worth protecting here are the ones a reader would never
notice going wrong.

AUTOSAVE MUST NOT BLANK. The wizard saves one answer per step, so a patch
carrying `brand_name` and nothing else must leave the other eleven alone.
The obvious implementation — write the whole model — silently empties
everything the customer answered on the previous eleven screens, and they
find out at the review page.

ANALYSIS MUST NOT OVERWRITE. A suggestion read off the customer's website
may fill a blank; it may never replace something the customer typed. Get
that wrong and running the analysis a second time quietly reverts an
afternoon of edits back to what a homepage said.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("MAILPILOT_DB", str(Path(tempfile.mkdtemp(prefix="brand-")) / "t.db"))
os.environ.setdefault("MAILPILOT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("MAILPILOT_SENDER", "0")

from app import brandprofile, db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh():
    db.init_db()
    db.execute("DELETE FROM brand_profile")
    brandprofile.ensure_row()
    yield


# ------------------------------------------------------------------ autosave


def test_a_single_answer_does_not_blank_the_others():
    brandprofile.save({"brand_name": "Beyondex"})
    brandprofile.save({"business_summary": "We build sales agents."})
    p = brandprofile.get()
    assert p["brand_name"] == "Beyondex"
    assert p["business_summary"] == "We build sales agents."


def test_the_step_is_remembered_so_a_return_visit_resumes():
    brandprofile.save({"current_step": 7})
    assert brandprofile.get()["current_step"] == 7


def test_the_step_cannot_go_outside_the_wizard():
    brandprofile.save({"current_step": 99})
    assert brandprofile.get()["current_step"] == brandprofile.TOTAL_STEPS
    brandprofile.save({"current_step": 0})
    assert brandprofile.get()["current_step"] == 1


# ------------------------------------------------------------- confirmation


def test_answering_marks_a_field_confirmed():
    brandprofile.save({"brand_name": "Beyondex"})
    assert "brand_name" in brandprofile.get()["confirmed"]


def test_analysis_does_not_confirm_anything():
    """Storing what a website said is not the customer answering."""
    brandprofile.save({"analysis": {"suggestions": {"business_summary": "x"}}}, confirm=False)
    assert brandprofile.get()["confirmed"] == []


# ------------------------------------------------------------------ cleaning


def test_only_tones_this_product_knows_are_kept():
    """An unknown string here would reach the generator as an instruction
    nobody wrote."""
    brandprofile.save({"brand_voice": ["professional", "swashbuckling", "direct"]})
    assert brandprofile.get()["brand_voice"] == ["professional", "direct"]


def test_offers_keep_their_shape_and_drop_the_nameless():
    brandprofile.save({"offers": [
        {"name": "Sales agent", "description": "Answers first"},
        {"name": "", "description": "orphaned"},
        "Just a string",
    ]})
    offers = brandprofile.get()["offers"]
    assert offers == [
        {"name": "Sales agent", "description": "Answers first"},
        {"name": "Just a string", "description": ""},
    ]


def test_empty_list_entries_are_dropped():
    brandprofile.save({"customer_outcomes": ["Faster replies", "   ", ""]})
    assert brandprofile.get()["customer_outcomes"] == ["Faster replies"]


# --------------------------------------------------------------- the pro gate


def _fill_the_six():
    brandprofile.save({
        "brand_name": "Beyondex",
        "business_summary": "We build sales agents.",
        "offers": [{"name": "Sales agent", "description": "Answers first"}],
        "ideal_customer_profile": "Small importers",
        "customer_outcomes": ["Faster replies"],
        "brand_voice": ["professional"],
    })


def test_professional_mode_is_refused_until_the_six_are_answered():
    assert brandprofile.completeness()["proReady"] is False
    _fill_the_six()
    assert brandprofile.completeness()["proReady"] is True


def test_the_gate_names_exactly_what_is_missing():
    """So the panel can send the reader to the question rather than saying
    "incomplete" and leaving them to hunt."""
    brandprofile.save({"brand_name": "Beyondex"})
    missing = brandprofile.completeness()["missingForPro"]
    assert "brand_name" not in missing
    assert "business_summary" in missing


def test_an_optional_question_never_blocks_sending():
    """Proof and forbidden claims are optional by design: a business with
    neither can still write something true and specific."""
    _fill_the_six()
    c = brandprofile.completeness()
    assert c["proReady"] is True
    assert c["complete"] is False   # still questions left, and that is fine


# ------------------------------------------------------------- the prompt


def test_a_business_with_no_proof_is_told_not_to_cite_any():
    """The most damaging thing this generator could do is invent a case
    study, so silence about proof is not enough — it is forbidden aloud."""
    _fill_the_six()
    text = brandprofile.as_prompt()
    assert "NO proof points" in text
    assert "Do not cite results" in text


def test_forbidden_claims_reach_the_prompt_as_a_prohibition():
    _fill_the_six()
    brandprofile.save({"forbidden_claims": ["never mention price"]})
    text = brandprofile.as_prompt()
    assert "NEVER" in text
    assert "never mention price" in text


def test_the_prompt_leaves_out_what_was_never_answered():
    """An empty heading invites the model to fill it in."""
    brandprofile.save({"brand_name": "Beyondex"})
    text = brandprofile.as_prompt()
    assert "Beyondex" in text
    assert "Why choose it over alternatives" not in text
