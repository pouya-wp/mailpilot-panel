"""Sign-in brute-force protection.

This is about to sit on a public IP with a known-good email address in it, so
the tests are written against what an attacker actually does: guess the same
account repeatedly, and spray many accounts from one machine.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-throttle-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

from fastapi.testclient import TestClient  # noqa: E402

from app import db, throttle  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

GOOD = {"email": "pouya@acme.io", "password": "mailpilot"}
BAD = {"email": "pouya@acme.io", "password": "wrong-password"}


@pytest.fixture(scope="module")
def client():
    db.init_db()
    seed(force=True)
    with TestClient(app) as c:
        yield c
    db.close()


@pytest.fixture(autouse=True)
def clean():
    throttle.reset()
    yield
    throttle.reset()


# =================================================================== unit


def test_the_door_closes_after_enough_failures():
    for _ in range(throttle.MAX_PER_ACCOUNT):
        throttle.check("a@b.co", "1.1.1.1")
        throttle.failed("a@b.co", "1.1.1.1")

    with pytest.raises(throttle.TooManyAttempts):
        throttle.check("a@b.co", "1.1.1.1")


def test_a_correct_password_forgives_earlier_fumbles():
    for _ in range(throttle.MAX_PER_ACCOUNT - 1):
        throttle.failed("a@b.co", "1.1.1.1")
    throttle.succeeded("a@b.co", "1.1.1.1")

    # the counter is clear, so the next few mistakes are fine again
    for _ in range(throttle.MAX_PER_ACCOUNT - 1):
        throttle.check("a@b.co", "1.1.1.1")
        throttle.failed("a@b.co", "1.1.1.1")


def test_spraying_many_accounts_from_one_machine_is_caught():
    """The per-account counter never sees this; the per-IP one does."""
    for i in range(throttle.MAX_PER_IP):
        throttle.check(f"victim{i}@b.co", "9.9.9.9")
        throttle.failed(f"victim{i}@b.co", "9.9.9.9")

    with pytest.raises(throttle.TooManyAttempts):
        throttle.check("someone-new@b.co", "9.9.9.9")


def test_one_locked_account_does_not_lock_a_different_one():
    for _ in range(throttle.MAX_PER_ACCOUNT):
        throttle.failed("locked@b.co", "1.1.1.1")
    throttle.check("other@b.co", "2.2.2.2")  # must not raise


def test_the_window_expires(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(throttle.time, "monotonic", lambda: clock["t"])

    for _ in range(throttle.MAX_PER_ACCOUNT):
        throttle.failed("a@b.co", "1.1.1.1")
    with pytest.raises(throttle.TooManyAttempts):
        throttle.check("a@b.co", "1.1.1.1")

    clock["t"] += throttle.WINDOW_SECONDS + 1
    throttle.check("a@b.co", "1.1.1.1")  # forgiven


def test_the_error_says_how_long_to_wait():
    for _ in range(throttle.MAX_PER_ACCOUNT):
        throttle.failed("a@b.co", "1.1.1.1")
    with pytest.raises(throttle.TooManyAttempts) as caught:
        throttle.check("a@b.co", "1.1.1.1")
    assert 0 < caught.value.retry_after <= throttle.WINDOW_SECONDS + 1


# ============================================================== endpoint


def test_repeated_guesses_get_429_not_401(client):
    for _ in range(throttle.MAX_PER_ACCOUNT):
        assert client.post("/api/auth/login", json=BAD).status_code == 401

    blocked = client.post("/api/auth/login", json=BAD)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_the_right_password_is_refused_too_once_locked(client):
    """Deliberate: a locked account stays locked for the window, or the lock
    would only inconvenience someone who does not know the password."""
    for _ in range(throttle.MAX_PER_ACCOUNT):
        client.post("/api/auth/login", json=BAD)

    assert client.post("/api/auth/login", json=GOOD).status_code == 429


def test_signing_in_normally_is_unaffected(client):
    for _ in range(3):
        assert client.post("/api/auth/login", json=GOOD).status_code == 200
