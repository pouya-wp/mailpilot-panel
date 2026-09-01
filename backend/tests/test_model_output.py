"""The model's output has a shape only by request, not by contract.

A JSON shape in a prompt is a request. The model mostly honours it and
sometimes does not — it returns a number where the shape says a list, a string
where it says an object, a reply of a quarter of a megabyte. Every one of
those reached code that assumed otherwise.

Two of them 500'd the whole request, which in the panel looks like the agent
being down. The third went to the browser at 244KB and froze the tab laying it
out. None of them are the model misbehaving; they are all this side trusting
something it was never given.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-shape-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
os.environ["MAILPILOT_SENDER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import bootstrap  # noqa: E402

#: Everything the client reads without checking. A missing key here is a
#: `undefined is not a function` in the browser.
REQUIRED = ("reply", "intent", "draft", "audience", "steps", "needs", "did", "pending")


@pytest.fixture(scope="module")
def client():
    db.init_db()
    bootstrap()
    db.update("deployment", "1", {"ai_key": "sk-test"})
    with TestClient(app) as c:
        yield c
    db.close()


@pytest.fixture(scope="module")
def auth(client):
    from app.config import settings

    r = client.post("/api/auth/login",
                    json={"email": settings.demo_email, "password": settings.demo_password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ask(client, auth, monkeypatch, payload):
    from app.routers import ai as ai_router

    monkeypatch.setattr(ai_router.brain, "converse", lambda *a, **k: dict(payload))
    return client.post("/api/ai/ask", headers=auth, json={"message": "do a thing", "lang": "en"})


@pytest.mark.parametrize("label,payload", [
    ("empty object", {}),
    ("nulls", {"reply": None, "draft": None, "actions": None, "steps": None, "needs": None}),
    ("wrong types", {"reply": 123, "draft": "not a dict", "actions": "nope",
                     "steps": "x", "needs": 5}),
    ("draft with no body", {"reply": "ok", "draft": {"subject": "S", "body": [], "cta": ""}}),
    ("body of numbers", {"reply": "ok", "draft": {"subject": "S", "body": [1, 2, 3], "cta": ""}}),
    ("invented segment", {"reply": "ok", "audience": {"segmentId": "seg-nope", "reason": "x"}}),
    ("junk actions", {"reply": "ok", "actions": [{"tool": "send_email", "args": "not a dict"},
                                                 {"nope": 1}, None, "string"]}),
    ("deep nesting", {"reply": "ok",
                      "draft": {"subject": "S", "body": [{"a": {"b": {"c": 1}}}], "cta": ""}}),
    ("lists where strings go", {"reply": ["a", "b"], "intent": ["x"]}),
])
def test_the_panel_survives_whatever_the_model_returns(client, auth, monkeypatch, label, payload):
    r = ask(client, auth, monkeypatch, payload)
    assert r.status_code < 500, f"{label} -> {r.status_code} {r.text[:160]}"
    body = r.json()
    missing = [k for k in REQUIRED if k not in body]
    assert not missing, f"{label} -> response is missing {missing}, which the panel reads"
    assert isinstance(body["steps"], list) and isinstance(body["needs"], list)
    assert isinstance(body["reply"], str)


def test_a_runaway_reply_does_not_reach_the_browser(client, auth, monkeypatch):
    """Measured at 244KB before this. The browser lays it out, measures it and
    paints it; on a phone that is a frozen tab."""
    r = ask(client, auth, monkeypatch,
            {"reply": "x" * 200_000, "steps": ["y" * 50_000] * 20, "needs": ["z" * 50_000]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["reply"]) <= 4000
    assert all(len(s) <= 400 for s in body["steps"])
    assert len(r.text) < 40_000, f"response is still {len(r.text)} bytes"


def test_an_action_with_junk_arguments_is_refused_not_crashed(client):
    """`execute` checked the action was an object and not its arguments."""
    from app import tools

    done, pending = tools.execute([
        {"tool": "send_email", "args": "not a dict"},
        {"tool": "add_contacts", "args": ["also", "not", "a", "dict"]},
        {"tool": "send_email", "args": None},
    ])
    assert pending == []
    assert len(done) == 3
    assert all(not d["ok"] for d in done)
    assert all("object" in d["error"] for d in done)


def test_summarise_never_raises_on_model_input():
    """It is called while building the approval button, so raising there loses
    the whole turn — including the actions that were fine."""
    from app import tools

    for args in ("string", None, 42, ["a"], {"to": "one@example.com", "subject": "S"}):
        assert isinstance(tools.summarise("send_email", args), str)
        assert isinstance(tools.summarise("send_campaign", args), str)
