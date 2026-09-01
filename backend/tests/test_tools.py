"""What the agent is allowed to do on its own.

The tests that matter here are the refusals. A tool layer that adds a contact
correctly but can be talked into mailing a list is not a working feature, it is
an incident — so most of this file is about the things the model asks for and
does not get.

Nothing reaches Gmail: `MAILPILOT_SENDER=0`, and no mailbox is connected except
where a test connects a fake one to reach the code past that check.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-tools-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
os.environ["MAILPILOT_SENDER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import db, deployment, tools  # noqa: E402
from app.domain import iso  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.security import new_id  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db.init_db()
    seed(force=True)
    with TestClient(app) as c:
        yield c
    db.close()


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/login", json={"email": "pouya@acme.io", "password": "mailpilot"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _approve_mode(client):
    """The default posture, and the one the interesting tests need."""
    db.update("deployment", "1", {"agent_autonomy": "approve"})
    yield
    db.update("deployment", "1", {"agent_autonomy": "approve"})


def _fresh_email(tag: str = "x") -> str:
    return f"{tag}-{os.urandom(4).hex()}@example.com"


# =========================================================== the safe/outward line


def test_saving_contacts_happens_without_asking():
    """Reversible and internal. Confirming it would be the clutter we removed."""
    email = _fresh_email("saved")
    done, pending = tools.execute([
        {"tool": "add_contacts", "args": {"people": [{"email": email, "name": "Ali"}]}}
    ])
    assert pending == []
    assert done[0]["ok"] and done[0]["result"]["added"] == 1
    assert db.one("SELECT 1 FROM contacts WHERE email = ?", (email,))


def test_sending_mail_is_never_carried_out_on_the_models_say_so():
    """The one that matters. A model asking to send is a proposal, not an act."""
    done, pending = tools.execute([
        {"tool": "send_email", "args": {"to": ["stranger@example.com"],
                                        "subject": "Hi", "body": ["hello"]}}
    ])
    assert done == []
    assert len(pending) == 1
    assert pending[0]["tool"] == "send_email"
    assert pending[0]["outward"] is True
    # and the operator is shown what they are approving
    assert "stranger@example.com" in pending[0]["says"]


def test_suggest_mode_holds_back_even_the_safe_actions():
    """The deployment said propose-only; that covers everything."""
    db.update("deployment", "1", {"agent_autonomy": "suggest"})
    done, pending = tools.execute([
        {"tool": "add_contacts", "args": {"people": [{"email": _fresh_email()}]}}
    ])
    assert done == [] and len(pending) == 1


def test_auto_mode_is_the_only_thing_that_lets_mail_go_unattended():
    """A human decision made once in Settings — not one the model can make."""
    db.update("deployment", "1", {"agent_autonomy": "auto"})
    done, pending = tools.execute([
        {"tool": "send_email", "args": {"to": ["a@example.com"], "subject": "S", "body": ["b"]}}
    ])
    assert pending == []
    # it ran, and failed honestly on the missing mailbox rather than silently
    assert done[0]["ok"] is False and "mailbox" in done[0]["error"]


# ================================================================== validation


def test_a_hallucinated_tool_is_ignored():
    done, pending = tools.execute([{"tool": "delete_everything", "args": {}}])
    assert done == [] and pending == []


def test_a_hallucinated_segment_does_not_become_a_campaign():
    with pytest.raises(tools.ToolError, match="no segment"):
        tools.run("create_campaign", {"name": "N", "subject": "S", "body": ["b"],
                                      "segmentId": "seg-invented"})


def test_a_junk_address_is_refused_rather_than_stored():
    done, _ = tools.execute([
        {"tool": "add_contacts", "args": {"people": [
            {"email": "not-an-address"}, {"email": ""}, {"email": _fresh_email("good")},
        ]}}
    ])
    assert done[0]["result"]["added"] == 1
    # and the operator is told, rather than three rows quietly vanishing
    assert done[0]["result"]["invalid"] == 2


@pytest.mark.parametrize("address", [
    "ali@example",        # no TLD
    "ali@.com",           # empty domain label
    "ali..rez@shop.com",  # consecutive dots
    "ali rez@shop.com",   # a space
    "ali@localhost",      # not routable off the machine
    "@shop.com",
    "ali@",
])
def test_addresses_that_would_bounce_never_reach_the_list(address):
    """These all passed the old check, which was "has an @ and no spaces".

    They matter because nobody eyeballs them: the model reads a pasted list and
    the panel stores the result. A bad address is a bounce, and bounces are how
    a sending domain loses its reputation.
    """
    with pytest.raises(tools.ToolError):
        tools._email(address)


@pytest.mark.parametrize("raw,clean", [
    ("Ali@Example.COM", "ali@example.com"),
    ("  ali@shop.ir  ", "ali@shop.ir"),
    ("<ali@example.com>", "ali@example.com"),
    ("Ali Rezaei <ali@example.com>", "ali@example.com"),
])
def test_a_usable_address_is_normalised_not_rejected(raw, clean):
    """Pasted from a mail header, it still has to land as the address."""
    assert tools._email(raw) == clean


def test_someone_who_unsubscribed_is_not_re_added_by_the_agent():
    """The list is theirs, not the model's."""
    email = _fresh_email("gone")
    db.insert("suppression", {"id": new_id("sup"), "email": email,
                              "reason": "unsub", "created_at": iso()})
    done, _ = tools.execute([
        {"tool": "add_contacts", "args": {"people": [{"email": email}]}}
    ])
    assert done[0]["result"]["added"] == 0
    assert done[0]["result"]["refusedAsUnsubscribed"] == 1


def test_an_unsubscribed_address_is_dropped_from_a_send():
    email = _fresh_email("blocked")
    db.insert("suppression", {"id": new_id("sup"), "email": email,
                              "reason": "unsub", "created_at": iso()})
    with pytest.raises(tools.ToolError, match="unsubscribed"):
        tools.run("send_email", {"to": [email], "subject": "S", "body": ["b"]})


def test_a_body_is_escaped_on_its_way_into_html():
    html = tools._body_html(["5 < 6 & you know it"])
    assert "&lt;" in html and "&amp;" in html and "<script" not in html


def test_one_failing_action_does_not_lose_the_others():
    email = _fresh_email("survivor")
    done, _ = tools.execute([
        {"tool": "create_campaign", "args": {"segmentId": "seg-invented", "name": "n",
                                             "subject": "s", "body": ["b"]}},
        {"tool": "add_contacts", "args": {"people": [{"email": email}]}},
    ])
    assert done[0]["ok"] is False
    assert done[1]["ok"] is True and done[1]["result"]["added"] == 1


def test_a_turn_cannot_queue_unlimited_actions():
    many = [{"tool": "find_contacts", "args": {}} for _ in range(40)]
    done, pending = tools.execute(many)
    assert len(done) + len(pending) <= tools.MAX_PER_TURN


# =================================================================== approval


def test_the_signature_is_what_makes_the_button_mean_anything(client, auth):
    """Approving "email two people" must not be redeemable for anything else."""
    args = {"to": ["one@example.com"], "subject": "S", "body": ["b"]}
    sig = tools.sign("send_email", args)

    assert tools.blob_ok("send_email", args, sig) is True
    # the same signature, a bigger audience
    assert tools.blob_ok("send_email", {**args, "to": ["everyone@example.com"]}, sig) is False
    # the same signature, a different tool
    assert tools.blob_ok("send_campaign", args, sig) is False


def test_the_signature_survives_a_json_round_trip():
    """The browser re-serialises the args; key order is not ours to assume."""
    import json

    args = {"subject": "S", "to": ["a@example.com"], "body": ["b"]}
    sig = tools.sign("send_email", args)
    assert tools.blob_ok("send_email", json.loads(json.dumps(args)), sig) is True


def test_confirm_refuses_an_action_that_was_never_proposed(client, auth):
    r = client.post("/api/ai/confirm", headers=auth, json={
        "tool": "send_email",
        "args": {"to": ["victim@example.com"], "subject": "S", "body": ["b"]},
        "sig": "obviously-not-a-real-signature",
    })
    assert r.status_code == 400
    assert "does not match" in r.json()["detail"]


def test_confirm_runs_a_properly_signed_action(client, auth):
    args = {"people": [{"email": _fresh_email("confirmed"), "name": "Approved"}]}
    r = client.post("/api/ai/confirm", headers=auth, json={
        "tool": "add_contacts", "args": args, "sig": tools.sign("add_contacts", args),
    })
    assert r.status_code == 200, r.text
    assert r.json()["result"]["added"] == 1


def test_a_viewer_who_may_chat_may_not_authorise_mail(client):
    """`content.edit` gets you a draft; `campaigns.send` gets it out the door."""
    from app.domain import PERMISSIONS

    assert "viewer" in PERMISSIONS["analytics.view"]
    assert "viewer" not in PERMISSIONS["campaigns.send"]


# ==================================================================== the prompt


def test_every_advertised_tool_actually_exists():
    """The catalogue is what the model is told it can call."""
    advertised = {t["name"] for t in tools.CATALOG}
    assert advertised == set(tools.RUNNERS)


def test_the_description_warns_which_ones_reach_people():
    text = tools.describe()
    for name in tools.OUTWARD:
        assert name in text
    assert "reaches real inboxes" in text
