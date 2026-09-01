"""Saved conversations.

The interesting tests here are the ones about ownership. Two people share this
panel, and a half-finished thought about what to send a customer is not
something either of them agreed to show the other.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-chats-"))
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


def _login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "mailpilot"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def owner(client):
    return _login(client, "pouya@acme.io")


@pytest.fixture(scope="module")
def other(client):
    return _login(client, "sara@acme.io")


# =================================================================== basics


def test_a_conversation_records_both_sides(client, owner):
    chat = client.post("/api/chats", headers=owner).json()

    client.post(f"/api/chats/{chat['id']}/turns",
                json={"role": "user", "text": "write a spring promo"}, headers=owner)
    client.post(f"/api/chats/{chat['id']}/turns",
                json={"role": "agent", "text": "Here is a draft.",
                      "meta": {"intent": "campaign"}}, headers=owner)

    full = client.get(f"/api/chats/{chat['id']}", headers=owner).json()
    assert [t["role"] for t in full["turns"]] == ["user", "agent"]
    assert full["turns"][0]["text"] == "write a spring promo"
    assert full["turns"][1]["meta"]["intent"] == "campaign"


def test_the_title_comes_from_the_first_thing_said(client, owner):
    """Naming it with a model call would cost a request and a wait to produce
    what the first sentence already says."""
    chat = client.post("/api/chats", headers=owner).json()
    assert chat["title"] == ""

    client.post(f"/api/chats/{chat['id']}/turns",
                json={"role": "user", "text": "win back everyone who went quiet"},
                headers=owner)

    listed = client.get("/api/chats", headers=owner).json()["items"]
    mine = next(c for c in listed if c["id"] == chat["id"])
    assert mine["title"] == "win back everyone who went quiet"


def test_a_long_first_message_is_trimmed(client, owner):
    chat = client.post("/api/chats", headers=owner).json()
    client.post(f"/api/chats/{chat['id']}/turns",
                json={"role": "user", "text": "x" * 300}, headers=owner)

    listed = client.get("/api/chats", headers=owner).json()["items"]
    title = next(c for c in listed if c["id"] == chat["id"])["title"]
    assert len(title) <= 61 and title.endswith("…")


def test_the_title_is_not_overwritten_by_later_messages(client, owner):
    chat = client.post("/api/chats", headers=owner).json()
    for text in ("first thing", "second thing", "third thing"):
        client.post(f"/api/chats/{chat['id']}/turns",
                    json={"role": "user", "text": text}, headers=owner)

    listed = client.get("/api/chats", headers=owner).json()["items"]
    assert next(c for c in listed if c["id"] == chat["id"])["title"] == "first thing"


def test_the_most_recent_conversation_is_first(client, owner):
    a = client.post("/api/chats", headers=owner).json()
    b = client.post("/api/chats", headers=owner).json()
    client.post(f"/api/chats/{a['id']}/turns",
                json={"role": "user", "text": "touched later"}, headers=owner)

    order = [c["id"] for c in client.get("/api/chats", headers=owner).json()["items"]]
    assert order.index(a["id"]) < order.index(b["id"])


def test_a_turn_must_be_from_one_of_the_two_parties(client, owner):
    chat = client.post("/api/chats", headers=owner).json()
    r = client.post(f"/api/chats/{chat['id']}/turns",
                    json={"role": "system", "text": "sneaky"}, headers=owner)
    assert r.status_code == 422


# ================================================================ ownership


def test_one_person_cannot_read_another_persons_conversation(client, owner, other):
    chat = client.post("/api/chats", headers=owner).json()
    client.post(f"/api/chats/{chat['id']}/turns",
                json={"role": "user", "text": "something private"}, headers=owner)

    # 404, not 403: confirming it exists is itself a disclosure
    assert client.get(f"/api/chats/{chat['id']}", headers=other).status_code == 404


def test_one_person_cannot_write_into_another_persons_conversation(client, owner, other):
    chat = client.post("/api/chats", headers=owner).json()
    r = client.post(f"/api/chats/{chat['id']}/turns",
                    json={"role": "user", "text": "hello"}, headers=other)
    assert r.status_code == 404


def test_one_person_cannot_delete_another_persons_conversation(client, owner, other):
    chat = client.post("/api/chats", headers=owner).json()
    assert client.delete(f"/api/chats/{chat['id']}", headers=other).status_code == 404
    assert client.get(f"/api/chats/{chat['id']}", headers=owner).status_code == 200


def test_the_list_shows_only_your_own(client, owner, other):
    mine = client.post("/api/chats", headers=owner).json()
    theirs = client.post("/api/chats", headers=other).json()

    owner_ids = {c["id"] for c in client.get("/api/chats", headers=owner).json()["items"]}
    other_ids = {c["id"] for c in client.get("/api/chats", headers=other).json()["items"]}

    assert mine["id"] in owner_ids and mine["id"] not in other_ids
    assert theirs["id"] in other_ids and theirs["id"] not in owner_ids


def test_signing_out_is_required(client):
    assert client.get("/api/chats").status_code == 401


# =================================================================== delete


def test_deleting_takes_the_turns_with_it(client, owner):
    chat = client.post("/api/chats", headers=owner).json()
    client.post(f"/api/chats/{chat['id']}/turns",
                json={"role": "user", "text": "gone soon"}, headers=owner)

    assert client.delete(f"/api/chats/{chat['id']}", headers=owner).status_code == 204
    assert client.get(f"/api/chats/{chat['id']}", headers=owner).status_code == 404
    # explicitly, because SQLite only enforces cascades when the pragma is on
    left = db.scalar("SELECT COUNT(*) FROM chat_turns WHERE chat_id = ?",
                     (chat["id"],), default=0)
    assert left == 0


def test_a_conversation_can_be_renamed(client, owner):
    chat = client.post("/api/chats", headers=owner).json()
    r = client.patch(f"/api/chats/{chat['id']}", json={"title": "Spring campaign"},
                     headers=owner)
    assert r.status_code == 200
    assert r.json()["title"] == "Spring campaign"
