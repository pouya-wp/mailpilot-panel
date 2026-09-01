"""Serving the built panel.

This block only activates when `MAILPILOT_WEB` points at a directory, which no
other test sets — so a `NameError` in it passed 141 green tests and then broke
every page load in production. The whole file exists because that happened.

It also covers the path-traversal guard, which is the one genuinely dangerous
thing about serving files by name from a user-supplied path.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEB = Path(tempfile.mkdtemp(prefix="mailpilot-web-"))
DATA = Path(tempfile.mkdtemp(prefix="mailpilot-static-"))


@pytest.fixture(scope="module")
def client():
    """A fresh app import with the static block switched ON."""
    (WEB / "index.html").write_text("<!doctype html><title>Panel</title>", encoding="utf-8")
    (WEB / "assets").mkdir(exist_ok=True)
    (WEB / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    # something outside the web root, for the traversal test to aim at
    (DATA / "secret.txt").write_text("do not serve me", encoding="utf-8")

    os.environ["MAILPILOT_WEB"] = str(WEB)
    os.environ["MAILPILOT_DB"] = str(DATA / "static-test.db")
    os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

    from app import db, main

    importlib.reload(main)          # re-run the module with MAILPILOT_WEB set
    with TestClient(main.app) as c:
        yield c
    db.close()
    os.environ.pop("MAILPILOT_WEB", None)


def test_the_app_shell_is_served_at_the_root(client):
    r = client.get("/")
    assert r.status_code == 200, r.text
    assert "<title>Panel</title>" in r.text


def test_a_real_asset_is_served(client):
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert "console.log" in r.text


def test_an_unknown_path_falls_back_to_the_shell(client):
    """A bookmark from an older build should open the app, not a bare 404."""
    r = client.get("/campaigns/c-123")
    assert r.status_code == 200
    assert "<title>Panel</title>" in r.text


def test_the_api_still_wins_over_the_catch_all(client):
    """The static mount is registered last precisely so it cannot shadow /api."""
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_an_unmatched_api_path_is_a_404_not_the_shell(client):
    """An /api path must answer like an API even when it matches nothing.

    The catch-all used to return the HTML shell with a 200 for these, so a
    client asking for JSON got `<!doctype html>` and never entered its error
    branch — the failure then surfaced as a parse error somewhere unrelated.
    """
    for path in ("/api/totally-made-up", "/api/auth/login", "/api/google/connect"):
        r = client.get(path)
        assert r.status_code == 404, f"{path} returned {r.status_code}"
        assert "<!doctype" not in r.text.lower(), f"{path} served the shell"


@pytest.mark.parametrize("attack", [
    "../secret.txt",
    "..%2fsecret.txt",
    "assets/../../secret.txt",
    "....//secret.txt",
])
def test_path_traversal_cannot_escape_the_web_root(client, attack):
    """Whatever it resolves to, it must never be the file outside the root."""
    r = client.get(f"/{attack}")
    assert "do not serve me" not in r.text
