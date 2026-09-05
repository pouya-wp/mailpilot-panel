"""The Gmail connection and the outbox.

No network. Everything here is either pure (building a MIME message, parsing a
Gmail payload) or database-level (queueing, suppression, scheduling), which is
where the bugs that matter actually live — the HTTP calls themselves are four
lines of urllib and fail loudly.

The state tests are the important ones. They are the difference between a
panel that sends through the customer's mailbox and a panel that sends through
whoever handed them a link.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-google-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
os.environ["MAILPILOT_SENDER"] = "0"  # nothing may reach Gmail from a test run

from fastapi.testclient import TestClient  # noqa: E402

from app import db, deployment, google, mailer  # noqa: E402
from app.domain import iso  # noqa: E402
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
def _clean_google(client):
    # depends on `client` so the database exists: the pure tests in this file
    # would otherwise trip the cleanup before init_db had ever run

    yield
    deployment.save_google(google_client_id="", google_secret="", google_refresh="",
                           google_email="", google_state="", google_connected_at="",
                           google_sync_at="")


def _with_client():
    deployment.save_google(google_client_id="cid.apps.googleusercontent.com",
                           google_secret="shhh")


# ================================================================== the URL


def test_the_consent_url_asks_for_offline_access_and_narrow_scopes():
    url = google.consent_url(client_id="cid", redirect_uri="https://p.example/api/google/callback",
                             state="abc123")
    q = parse_qs(urlparse(url).query)

    # without these two the panel gets an hour of access and then silently stops
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["state"] == ["abc123"]

    scopes = q["scope"][0].split(" ")
    assert "https://www.googleapis.com/auth/gmail.send" in scopes
    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    # the scope that would let this product delete someone's mail
    assert "https://mail.google.com/" not in scopes


def test_connect_refuses_before_the_oauth_client_is_configured(client, auth):
    r = client.post("/api/google/connect", headers=auth)
    assert r.status_code == 400
    assert "client id" in r.json()["detail"].lower()


def test_connect_returns_a_url_and_stores_the_state(client, auth):
    _with_client()
    r = client.post("/api/google/connect", headers=auth)
    assert r.status_code == 200

    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    assert state and deployment.get()["google_state"] == state
    # the value the implementer has to paste into the Google console
    assert r.json()["redirectUri"].endswith("/api/google/callback")


# ================================================================ the callback


def test_the_callback_refuses_a_state_it_did_not_mint(client):
    _with_client()
    deployment.save_google(google_state="the-real-one")

    r = client.get("/api/google/callback?code=x&state=an-attackers-value",
                   follow_redirects=False)
    assert r.status_code == 303
    assert "google=badstate" in r.headers["location"]
    # and nothing was stored
    assert not deployment.get()["google_refresh"]


def test_a_state_is_consumed_by_one_attempt(client):
    _with_client()
    deployment.save_google(google_state="single-use")

    client.get("/api/google/callback?code=&state=single-use", follow_redirects=False)
    assert deployment.get()["google_state"] == ""

    # replaying the same callback now fails the state check
    r = client.get("/api/google/callback?code=x&state=single-use", follow_redirects=False)
    assert "google=badstate" in r.headers["location"]


def test_a_refused_consent_comes_back_as_denied(client):
    r = client.get("/api/google/callback?error=access_denied", follow_redirects=False)
    assert r.status_code == 303
    assert "google=denied" in r.headers["location"]


def test_every_exit_lands_on_the_tab_that_explains_it(client):
    """Settings opens on the agent tab; the mailbox card is on the sending one.

    Without `tab=sending` the reader came back to a screen that said nothing
    about what had just happened, because the component holding the message
    was not mounted.
    """
    _with_client()
    deployment.save_google(google_state="s1")
    for url in ("/api/google/callback?error=access_denied",
                "/api/google/callback?code=x&state=wrong",
                "/api/google/callback?code=&state=s1"):
        location = client.get(url, follow_redirects=False).headers["location"]
        assert "tab=sending" in location, location
        assert "google=" in location, location


# ================================================================== secrets


def test_the_status_endpoint_never_returns_the_credentials(client, auth):
    deployment.save_google(google_client_id="cid", google_secret="shhh",
                           google_refresh="refresh-token-worth-more-than-the-password",
                           google_email="agent@example.com", google_connected_at=iso())
    body = client.get("/api/google/status", headers=auth).text

    assert "refresh-token-worth-more-than-the-password" not in body
    assert "shhh" not in body
    assert "agent@example.com" in body  # the one thing a person needs to see
    assert '"hasSecret":true' in body.replace(" ", "")


def test_saving_the_client_without_a_secret_keeps_the_installed_one(client, auth):
    _with_client()
    client.put("/api/google/client", headers=auth, json={"clientId": "corrected-id"})
    d = deployment.get()
    assert d["google_client_id"] == "corrected-id"
    assert d["google_secret"] == "shhh"


def test_disconnect_forgets_the_mailbox(client, auth):
    deployment.save_google(google_refresh="r", google_email="a@b.c", google_connected_at=iso())
    out = client.post("/api/google/disconnect", headers=auth).json()
    assert out["connected"] is False
    assert deployment.get()["google_refresh"] == ""


# ============================================================= google's errors


def test_googles_json_becomes_a_sentence_someone_can_act_on():
    """The real 403 from a project with the Gmail API switched off."""
    body = (
        '{"error": {"code": 403, "message": "Gmail API has not been used in '
        'project 301003310707 before or it is disabled. Enable it by visiting '
        'https://console.developers.google.com/apis/api/gmail.googleapis.com/'
        'overview?project=301003310707 then retry.", "errors": [{"domain": '
        '"usageLimits", "reason": "accessNotConfigured"}], "status": '
        '"PERMISSION_DENIED"}}'
    )
    out = google._explain(403, body)
    assert "APIs & Services" in out and "Gmail API" in out
    # none of the JSON, and none of the console URL, reaches the reader
    assert "{" not in out and "http" not in out


def test_a_revoked_grant_says_to_reconnect():
    out = google._explain(400, '{"error":"invalid_grant","error_description":"revoked"}')
    assert "Reconnect" in out


def test_an_unmapped_error_still_quotes_google_rather_than_shrugging():
    out = google._explain(400, '{"error":{"code":400,"message":"Invalid From header"}}')
    assert "Invalid From header" in out


def test_a_non_json_body_does_not_explode():
    assert "500" in google._explain(500, "<html>gateway timeout</html>")


# ======================================================== the sending address


def test_a_from_address_gmail_cannot_use_is_reported(client, auth):
    deployment.save_google(google_refresh="r", google_email="agent@gmail.com")
    db.update("deployment", "1", {"from_email": "hello@someshop.com"})
    assert deployment.google_status()["fromMismatch"] is True

    db.update("deployment", "1", {"from_email": "agent@gmail.com"})
    assert deployment.google_status()["fromMismatch"] is False

    # and an empty one is not a mismatch — it falls back to the mailbox
    db.update("deployment", "1", {"from_email": ""})
    assert deployment.google_status()["fromMismatch"] is False


# ================================================================== the MIME


def test_a_message_carries_a_plain_part_beside_the_html():
    raw = google.build_message(
        to="reader@example.com", sender="agent@example.com", sender_name="Nova",
        subject="Spring sale", html="<h1>Spring</h1><p>Ten percent off.</p>",
        reply_to="replies@example.com",
    )
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()

    assert "multipart/alternative" in decoded
    assert "To: reader@example.com" in decoded
    assert "Nova <agent@example.com>" in decoded
    assert "Reply-To: replies@example.com" in decoded
    # the HTML-only campaign is what several filters score as spam
    assert "text/plain" in decoded and "text/html" in decoded
    assert "Ten percent off." in decoded


def test_the_plain_part_is_readable_rather_than_markup():
    text = google._strip_tags(
        "<style>p{color:red}</style><h1>Hello</h1><p>Line one</p><p>Line &amp; two</p>"
    )
    assert "<" not in text
    assert "color:red" not in text
    assert "Line & two" in text
    assert text.splitlines()[0] == "Hello"


def test_a_reply_body_is_found_however_the_sender_nested_it():
    def part(mime, text=None, parts=None):
        out = {"mimeType": mime}
        if text is not None:
            out["body"] = {"data": base64.urlsafe_b64encode(text.encode()).decode()}
        if parts:
            out["parts"] = parts
        return out

    payload = part("multipart/mixed", parts=[
        part("multipart/alternative", parts=[
            part("text/plain", "yes please, send it"),
            part("text/html", "<p>yes please, send it</p>"),
        ]),
        part("application/pdf"),
    ])
    assert google._body_text(payload) == "yes please, send it"


def test_html_only_replies_still_produce_text():
    data = base64.urlsafe_b64encode(b"<p>Sounds good</p>").decode()
    payload = {"mimeType": "text/html", "body": {"data": data}}
    assert google._body_text(payload) == "Sounds good"


def test_an_address_is_pulled_out_of_a_display_name():
    assert google.sender_address("Ali Reza <Ali@Example.COM>") == "ali@example.com"
    assert google.sender_address("plain@example.com") == "plain@example.com"
    assert google.sender_address("not an address") == ""


# ================================================================== the queue


def _campaign(status: str = "draft", scheduled_for=None) -> str:
    cid = f"c-test-{os.urandom(4).hex()}"
    db.insert("campaigns", {
        "id": cid, "name_en": "Q", "name_fa": "Q", "subject_en": "Hi", "subject_fa": "Hi",
        "body_en": "<p>Hi {{first_name}}</p>", "status": status,
        "scheduled_for": scheduled_for, "created_at": iso(), "updated_at": iso(),
    })
    return cid


def test_the_outbox_skips_suppressed_addresses():
    cid = _campaign()
    db.insert("suppression", {"id": f"s-{os.urandom(3).hex()}", "email": "blocked@example.com",
                              "reason": "unsub", "created_at": iso()})

    queued = mailer.enqueue(cid, recipients=[
        {"id": "c1", "email": "fine@example.com", "name": "Fine"},
        {"id": "c2", "email": "blocked@example.com", "name": "Blocked"},
    ])
    assert queued == 1
    assert mailer.progress(cid)["queued"] == 1


def test_queueing_the_same_campaign_twice_does_not_double_send():
    cid = _campaign()
    people = [{"id": "c1", "email": "one@example.com", "name": "One"}]
    assert mailer.enqueue(cid, recipients=people) == 1
    assert mailer.enqueue(cid, recipients=people) == 0
    assert mailer.progress(cid)["total"] == 1


def test_rows_without_a_usable_address_are_dropped_not_queued():
    cid = _campaign()
    queued = mailer.enqueue(cid, recipients=[
        {"id": "a", "email": "", "name": "Blank"},
        {"id": "b", "email": "not-an-address", "name": "Broken"},
        {"id": "c", "email": "  MIXED@Example.com  ", "name": "Spaced"},
    ])
    assert queued == 1
    row = db.one("SELECT email FROM outbox WHERE campaign_id = ?", (cid,))
    # normalised on the way in, so the suppression check can match it later
    assert row["email"] == "mixed@example.com"


def test_a_restart_requeues_a_send_that_was_in_flight():
    cid = _campaign()
    mailer.enqueue(cid, recipients=[{"id": "c1", "email": "midflight@example.com", "name": "M"}])
    db.execute("UPDATE outbox SET status = 'sending' WHERE campaign_id = ?", (cid,))

    assert mailer.recover_stuck() >= 1
    assert mailer.progress(cid)["queued"] == 1


def test_merge_tags_are_filled_per_recipient():
    out = mailer._personalise(
        "Hi {{first_name}}, unsubscribe at {{unsubscribe}}",
        {"id": "c-9", "email": "ali@example.com", "name": "Ali Reza"},
        "c-77",
    )
    assert out.startswith("Hi Ali,")
    # a campaign that ships the literal placeholder is a legal problem
    assert "{{unsubscribe}}" not in out
    # With no public URL and no support address there is nothing to point at,
    # so the tag resolves to a dead anchor — and `campaigns/send` refuses the
    # send outright in that state rather than mailing a broken opt-out. What
    # matters here is only that the literal placeholder never ships.
    assert "{{" not in out


def test_the_call_to_action_never_points_at_the_admin_panel(monkeypatch):
    """A recipient pressing "start a conversation" must not land on a login.

    `{{cta_url}}` used to resolve to `public_base()` first, which is this
    deployment's own admin panel — so an outreach email sent to a gold shop
    in Dubai offered a button to a MailPilot sign-in screen. It looked fine
    in the designer preview and was unusable to every person who got one.
    """
    from app import deployment

    monkeypatch.setattr(mailer, "public_base", lambda: "https://panel.example.com")
    monkeypatch.setattr(deployment, "get", lambda: {
        "support_email": "", "reply_to": "", "from_email": "",
        "google_email": "agent@example.com", "brand_name": "Northwind",
    })

    out = mailer._personalise("<a href='{{cta_url}}'>talk</a>",
                              {"id": "c-9", "email": "a@b.c", "name": "Ali"}, "c-77")

    assert "panel.example.com" not in out
    assert "mailto:agent@example.com" in out


def test_the_call_to_action_prefers_a_real_reply_address(monkeypatch):
    """The connected Gmail is the last resort, not the first choice."""
    from app import deployment

    monkeypatch.setattr(mailer, "public_base", lambda: "https://panel.example.com")
    monkeypatch.setattr(deployment, "get", lambda: {
        "support_email": "hello@northwind.com", "reply_to": "",
        "from_email": "", "google_email": "agent@example.com",
        "brand_name": "Northwind",
    })

    out = mailer._personalise("{{cta_url}}", {"id": "c-9", "email": "a@b.c", "name": "Ali"}, "c-77")
    assert out.startswith("mailto:hello@northwind.com")


def test_someone_with_no_name_still_gets_a_greeting():
    out = mailer._personalise("Hi {{first_name}}", {"id": "x", "email": "a@b.c", "name": ""}, "c-1")
    assert out == "Hi there"


# ============================================================== the schedule


def test_a_scheduled_campaign_starts_when_its_time_passes():
    from app.domain import ago_iso

    seg = db.one("SELECT id FROM segments LIMIT 1")
    cid = _campaign(status="scheduled", scheduled_for=ago_iso(days=1))
    db.update("campaigns", cid, {"segment_id": seg["id"]})

    assert mailer.promote_due() >= 1
    assert db.one("SELECT status FROM campaigns WHERE id = ?", (cid,))["status"] == "running"
    assert mailer.progress(cid)["queued"] > 0


def test_a_campaign_scheduled_for_later_is_left_alone():
    from datetime import datetime, timedelta, timezone

    later = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    seg = db.one("SELECT id FROM segments LIMIT 1")
    cid = _campaign(status="scheduled", scheduled_for=later)
    db.update("campaigns", cid, {"segment_id": seg["id"]})

    mailer.promote_due()
    assert db.one("SELECT status FROM campaigns WHERE id = ?", (cid,))["status"] == "scheduled"
    assert mailer.progress(cid)["total"] == 0


def test_the_sender_stays_off_when_the_deployment_says_so():
    """The switch this whole test file depends on."""
    mailer.start()
    assert mailer.status()["running"] is False


# ============================================ the promise at the top of mailer.py


def test_concurrent_drains_never_send_the_same_email_twice(client, monkeypatch):
    """`mailer` promises "IT NEVER SENDS TWICE". It did.

    Claiming a row was a SELECT followed by an UPDATE, and the gap between
    them is a race: two drains read the same row as `queued`, both mark it
    `sending`, and both send. Measured at three concurrent drains it produced
    eight messages for six recipients.

    Duplicate mail is the one delivery mistake recipients punish — they do not
    report it as a bug, they report it as spam.
    """
    import threading
    import time

    from app import deployment, google, mailer
    from app.routers.audience import segment_members
    from app.seed import ensure_default_segment

    ensure_default_segment()
    db.execute("DELETE FROM outbox")
    # whatever group this fixture actually has — the seeded database has its
    # own, so assuming `seg-everyone` trips the foreign key
    seg = db.one("SELECT id FROM segments LIMIT 1")["id"]

    cid = f"c-race-{os.urandom(3).hex()}"
    db.insert("campaigns", {
        "id": cid, "name_en": "Race", "name_fa": "Race", "subject_en": "S",
        "subject_fa": "S", "body_en": "<p>b</p>", "status": "running",
        "segment_id": seg, "created_at": iso(), "updated_at": iso(),
    })

    deployment.save_google(google_refresh="r", google_email="m@e.com")
    queued = mailer.enqueue(cid, recipients=segment_members(seg))
    assert queued > 1, "need several recipients for the race to be visible"

    sent, lock = [], threading.Lock()

    def slow_send(token, raw):
        # a real network call is not instant; the delay is what opens the gap
        time.sleep(0.01)
        with lock:
            sent.append(raw)
        return {"id": "m"}

    monkeypatch.setattr(mailer, "access_token", lambda: "stub")
    monkeypatch.setattr(google, "send_message", slow_send)
    monkeypatch.setattr(mailer, "SEND_INTERVAL", 0)

    threads = [threading.Thread(target=mailer._drain) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    deployment.save_google(google_refresh="", google_email="")

    assert len(sent) == queued, (
        f"{len(sent)} messages went out for {queued} recipients — duplicates")
    assert mailer.progress(cid)["sent"] == queued


def test_a_claimed_row_cannot_be_claimed_again(client):
    """The mechanism, directly: whoever flips queued->sending owns it."""
    from app import mailer

    db.execute("DELETE FROM outbox")
    cid = f"c-claim-{os.urandom(3).hex()}"
    mailer.enqueue(cid, recipients=[{"id": "x", "email": "one@example.com", "name": "O"}])

    first = mailer._claim()
    assert first is not None and first["email"] == "one@example.com"
    # the only queued row is now taken; a second drain must find nothing
    assert mailer._claim() is None
