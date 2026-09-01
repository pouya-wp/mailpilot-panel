"""The white-label layer.

These are the tests that matter commercially: if module gating is cosmetic, a
customer who was not sold billing can read billing by typing the URL, and the
whole "configure it per client" story is a lie. If the public config leaks the
API key, one unauthenticated GET hands over the implementer's OpenAI account.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-deploy-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402


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
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _restore(client, auth):
    """Each test gets the default deployment back, whatever the last one did."""
    yield
    client.put("/api/setup", json={
        "modules": ["campaigns", "audience", "inbox", "insights", "billing", "team",
                    "domains", "integrations"],
        "ai": {"clearKey": True},
    }, headers=auth)


# ============================================================== public config


def test_config_is_readable_without_signing_in(client):
    """The sign-in screen carries the customer's brand, so it must render
    before anyone has a token."""
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["brand"]["name"]
    assert "modules" in body


def test_public_config_never_leaks_the_api_key(client, auth):
    client.put("/api/setup", json={"ai": {"key": "sk-secret-value-1234"}}, headers=auth)
    raw = client.get("/api/config").text
    assert "sk-secret-value-1234" not in raw
    assert client.get("/api/config").json()["ai"]["configured"] is True


def test_owner_sees_only_a_masked_hint(client, auth):
    client.put("/api/setup", json={"ai": {"key": "sk-secret-value-1234"}}, headers=auth)
    ai = client.get("/api/setup", headers=auth).json()["ai"]
    assert ai["keyHint"].endswith("1234")
    assert "secret-value" not in ai["keyHint"]


# ================================================================ module gate


def test_disabling_a_module_makes_its_endpoint_unreachable(client, auth):
    assert client.get("/api/billing", headers=auth).status_code == 200

    client.put("/api/setup", json={
        "modules": ["campaigns", "audience", "inbox"],
    }, headers=auth)

    # not merely hidden in the navigation — refused
    assert client.get("/api/billing", headers=auth).status_code == 404
    assert "billing" not in client.get("/api/config").json()["modules"]


def test_core_modules_cannot_be_switched_off(client, auth):
    """An email agent with no campaigns is broken, not smaller."""
    client.put("/api/setup", json={"modules": []}, headers=auth)
    modules = client.get("/api/config").json()["modules"]
    assert "campaigns" in modules
    assert "audience" in modules


# ===================================================================== wizard


def test_setup_saves_one_step_at_a_time(client, auth):
    """The wizard writes each step as it is finished, so an interrupted setup
    resumes instead of starting over."""
    client.put("/api/setup", json={"brand": {"name": "Northwind"}}, headers=auth)
    client.put("/api/setup", json={"agent": {"name": "Ada", "tone": "direct"}}, headers=auth)

    body = client.get("/api/setup", headers=auth).json()
    assert body["brand"]["name"] == "Northwind"       # survived the second write
    assert body["agent"]["name"] == "Ada"
    assert body["agent"]["tone"] == "direct"


def test_setup_ignores_values_outside_the_allowed_set(client, auth):
    client.put("/api/setup", json={"agent": {"tone": "sarcastic", "autonomy": "whatever"}},
               headers=auth)
    agent = client.get("/api/setup", headers=auth).json()["agent"]
    assert agent["tone"] != "sarcastic"
    assert agent["autonomy"] in {"suggest", "approve", "auto"}


def test_an_empty_key_does_not_wipe_the_installed_one(client, auth):
    """A half-filled wizard step must not silently disable the AI."""
    client.put("/api/setup", json={"ai": {"key": "sk-installed-key-9999"}}, headers=auth)
    client.put("/api/setup", json={"ai": {"model": "gpt-4o"}}, headers=auth)
    assert client.get("/api/config").json()["ai"]["configured"] is True

    client.put("/api/setup", json={"ai": {"clearKey": True}}, headers=auth)
    assert client.get("/api/config").json()["ai"]["configured"] is False


def test_only_an_owner_can_read_the_setup(client):
    viewer = client.post("/api/auth/login", json={"email": "mia@acme.io", "password": "mailpilot"})
    headers = {"Authorization": f"Bearer {viewer.json()['access_token']}"}
    assert client.get("/api/setup", headers=headers).status_code == 403
    # but the branding is still public to them
    assert client.get("/api/config").status_code == 200


# ================================================================ AI fallback


def test_ask_answers_honestly_when_no_key_is_installed(client, auth):
    """No key is a setup state, not a server fault: 200 with an explanation,
    so the panel renders a sentence instead of an error card."""
    client.put("/api/setup", json={"ai": {"clearKey": True}}, headers=auth)
    r = client.post("/api/ai/ask", json={"message": "send a spring sale email"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["source"] == "unconfigured"
    assert body["reply"]


def test_compose_still_writes_with_no_provider(client, auth):
    """The local writer is what keeps a keyless install usable."""
    r = client.post("/api/ai/compose", json={"brief": "spring sale", "lang": "en"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["subject"] and body["body"]
    assert body["source"] == "local"


def test_research_refuses_clearly_with_no_key(client, auth):
    r = client.post("/api/ai/research", json={"query": "competitor pricing"}, headers=auth)
    assert r.status_code == 400
    assert "key" in r.json()["detail"].lower()


# ================================================================= wipe demo


def test_wipe_clears_operational_data_but_keeps_the_people(client, auth):
    assert client.get("/api/campaigns", headers=auth).json()["total"] > 0
    seats = len(client.get("/api/team", headers=auth).json())

    r = client.post("/api/setup/wipe-demo", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["rows"] > 0

    assert client.get("/api/campaigns", headers=auth).json()["total"] == 0
    assert client.get("/api/contacts", headers=auth).json()["total"] == 0
    # the team survives — you are not locked out of the panel you just cleaned
    assert len(client.get("/api/team", headers=auth).json()) == seats
    # and so does the deployment's own configuration
    assert client.get("/api/config").json()["brand"]["name"]


# ================================ the search toggle reaches the chat box


def test_the_chat_box_uses_the_searching_endpoint_when_search_is_on(client, auth, monkeypatch):
    """The toggle used to set a flag that only `/ai/research` read — an endpoint
    with no screen behind it — so the chat box never searched and said so."""
    from app import ai_provider, brain

    called = {}

    def fake_searching(settings, *, system, user, shape, max_tokens=1800, token_floor=0):
        called["searching"] = True
        return {"reply": "I looked it up.", "intent": "question",
                "_citations": [{"url": "https://example.com", "title": "Src"}]}

    def fake_plain(*a, **kw):
        called["plain"] = True
        return {"reply": "from memory", "intent": "question"}

    monkeypatch.setattr(brain, "complete_json_searching", fake_searching)
    monkeypatch.setattr(brain, "complete_json", fake_plain)

    client.put("/api/setup", json={"ai": {"key": "sk-x", "search": True}}, headers=auth)
    r = client.post("/api/ai/ask", json={"message": "what are competitors charging?"}, headers=auth)

    assert r.status_code == 200
    assert called.get("searching") is True
    assert called.get("plain") is None
    body = r.json()
    assert body["searched"] is True
    assert body["citations"][0]["url"] == "https://example.com"


def test_with_search_off_it_uses_the_plain_endpoint(client, auth, monkeypatch):
    from app import brain

    called = {}
    monkeypatch.setattr(brain, "complete_json_searching",
                        lambda *a, **kw: called.setdefault("searching", True) or {})
    monkeypatch.setattr(brain, "complete_json",
                        lambda *a, **kw: called.setdefault("plain", True) and
                        {"reply": "from memory", "intent": "question"})

    client.put("/api/setup", json={"ai": {"key": "sk-x", "search": False}}, headers=auth)
    r = client.post("/api/ai/ask", json={"message": "hello"}, headers=auth)

    assert r.status_code == 200
    assert called.get("plain") is True
    assert called.get("searching") is None
    assert r.json()["searched"] is False
