"""End-to-end tests against the real app.

Every test runs through the actual HTTP stack (routing, dependencies, auth,
validation, serialisation) against a throwaway database. Nothing is mocked,
so a green run means the API genuinely works rather than that the mocks agree
with each other.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# point the app at a scratch database BEFORE anything imports settings
_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-test-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
# The outbox is exercised as a queue here. Nothing may reach Gmail.
os.environ["MAILPILOT_SENDER"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.deployment import MODULES  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def client():
    db.init_db()
    seed(force=True)
    with TestClient(app) as c:
        yield c
    db.close()


@pytest.fixture(scope="module")
def token(client):
    r = client.post("/api/auth/login", json={"email": "pouya@acme.io", "password": "mailpilot"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def _every_module(client, token):
    """This file covers the WHOLE API surface, including the optional sections.

    A default deployment ships with the developer API switched off, so without
    this the api-key and webhook tests would be testing the module gate rather
    than the endpoints. Module gating has its own file.
    """
    client.put(
        "/api/setup",
        json={"modules": [m["id"] for m in MODULES]},
        headers={"Authorization": f"Bearer {token}"},
    )


# ================================================================ health


def test_health_reports_a_seeded_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["seeded"] is True


def test_meta_enumerations_are_served(client):
    body = client.get("/api/meta").json()
    assert "broadcast" in body["campaignTypes"]
    assert body["languages"] == ["en", "fa"]


# ================================================================ auth


def test_login_rejects_a_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "pouya@acme.io", "password": "nope"})
    assert r.status_code == 401


def test_login_does_not_reveal_whether_an_account_exists(client):
    missing = client.post("/api/auth/login", json={"email": "ghost@nowhere.io", "password": "x"})
    wrong = client.post("/api/auth/login", json={"email": "pouya@acme.io", "password": "x"})
    assert missing.status_code == wrong.status_code == 401
    assert missing.json()["detail"] == wrong.json()["detail"]


def test_protected_routes_refuse_anonymous_callers(client):
    assert client.get("/api/campaigns").status_code == 401


def test_a_tampered_token_is_refused(client, token):
    """Flip a character in the MIDDLE of the signature.

    Flipping the LAST character looks equivalent and is not: a 32-byte HMAC is
    43 base64url characters, and the final one carries only two significant
    bits — 4 of the 64 possible characters decode to the very same bytes. That
    made this test pass about fifteen runs in sixteen and fail the other one,
    with nothing wrong in the code. A middle character carries a full 6 bits,
    so any change to it always changes the signature.
    """
    head, payload, signature = token.split(".")
    middle = len(signature) // 2
    flipped = "a" if signature[middle] != "a" else "b"
    bad = f"{head}.{payload}.{signature[:middle]}{flipped}{signature[middle + 1:]}"

    assert bad != token
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_me_returns_the_role_and_its_permissions(client, auth):
    body = client.get("/api/auth/me", headers=auth).json()
    assert body["role"] == "owner"
    assert "billing.manage" in body["permissions"]


def test_refresh_rotates_and_burns_the_old_token(client):
    login = client.post("/api/auth/login",
                        json={"email": "sara@acme.io", "password": "mailpilot"}).json()
    first = login["refresh_token"]

    again = client.post("/api/auth/refresh", json={"refresh_token": first})
    assert again.status_code == 200
    assert again.json()["refresh_token"] != first

    # replaying the burnt token must fail
    assert client.post("/api/auth/refresh", json={"refresh_token": first}).status_code == 401


# ================================================================ roles


def test_an_analyst_cannot_send_a_campaign(client):
    tok = client.post("/api/auth/login",
                      json={"email": "mia@acme.io", "password": "mailpilot"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}
    # reading is fine
    assert client.get("/api/campaigns", headers=headers).status_code == 200
    # sending is not
    r = client.post("/api/campaigns/c-410/send", json={"mode": "now"}, headers=headers)
    assert r.status_code == 403


def test_a_viewer_cannot_write_contacts(client):
    tok = client.post("/api/auth/login",
                      json={"email": "kian@acme.io", "password": "mailpilot"}).json()
    # kian is 'pending' and has no password, so login must fail outright
    assert "access_token" not in tok


# ================================================================ campaigns


def test_campaign_list_paginates_and_filters(client, auth):
    body = client.get("/api/campaigns?size=3", headers=auth).json()
    assert len(body["items"]) == 3
    assert body["total"] >= 9

    running = client.get("/api/campaigns?status=running", headers=auth).json()
    assert running["total"] >= 1
    assert all(c["status"] == "running" for c in running["items"])


def test_campaign_search_matches_both_languages(client, auth):
    en = client.get("/api/campaigns?q=Summer", headers=auth).json()
    fa = client.get("/api/campaigns?q=تابستان", headers=auth).json()
    assert en["total"] >= 1 and fa["total"] >= 1
    assert en["items"][0]["id"] == fa["items"][0]["id"]


def test_every_name_carries_both_languages(client, auth):
    item = client.get("/api/campaigns?size=1", headers=auth).json()["items"][0]
    assert set(item["name"]) == {"en", "fa"}
    assert item["name"]["en"] and item["name"]["fa"]


def test_rates_are_computed_server_side(client, auth):
    c = client.get("/api/campaigns/c-401", headers=auth).json()
    expected = round(c["opens"] / c["sent"] * 100, 4)
    assert c["openRate"] == pytest.approx(expected, abs=0.01)


def _connect_a_mailbox() -> None:
    """Pretend Google has been through. No network, no real token.

    The send path only asks whether a refresh token EXISTS before queueing;
    using one is the worker's job and the worker is switched off here.
    """
    from app import deployment

    deployment.save_google(google_refresh="fake-refresh-token",
                           google_email="agent@example.com",
                           google_client_id="fake-client", google_secret="fake-secret")


def test_campaign_lifecycle(client, auth):
    created = client.post("/api/campaigns", headers=auth, json={
        "name": {"en": "Test blast", "fa": "ارسال آزمایشی"},
        "subject": {"en": "Hello", "fa": "سلام"},
        # a body, because a campaign with nothing in it is refused at send —
        # an empty message wrapped in the house template is still a real email
        "body": {"en": "Spring is here.", "fa": "بهار آمد."},
        "segment": "vip",
    })
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["status"] == "draft"
    # recipients came from the segment, not from the client
    assert created.json()["recipients"] == 25000

    # A reply-to, because a send with no way to unsubscribe is refused: an
    # opt-out that goes nowhere is the same as no opt-out.
    from app import db as _db
    _db.update("deployment", "1", {"reply_to": "replies@example.com"})

    # Sending for real needs a mailbox, and refusing early is the point.
    blocked = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
    assert blocked.status_code == 409 and "Gmail" in blocked.json()["detail"]

    _connect_a_mailbox()
    sent = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
    assert sent.status_code == 200 and sent.json()["status"] == "running"

    # the audience was resolved into one outbox row per subscribed contact
    progress = client.get(f"/api/campaigns/{cid}/progress", headers=auth).json()
    assert progress["total"] == progress["queued"] > 0

    paused = client.post(f"/api/campaigns/{cid}/pause", headers=auth)
    assert paused.json()["status"] == "paused"

    # pausing twice is a conflict, not a silent no-op
    assert client.post(f"/api/campaigns/{cid}/pause", headers=auth).status_code == 409

    assert client.post(f"/api/campaigns/{cid}/resume", headers=auth).json()["status"] == "running"
    # a running campaign cannot simply be deleted
    assert client.delete(f"/api/campaigns/{cid}", headers=auth).status_code == 409
    client.post(f"/api/campaigns/{cid}/pause", headers=auth)
    assert client.delete(f"/api/campaigns/{cid}", headers=auth).status_code == 204
    assert client.get(f"/api/campaigns/{cid}", headers=auth).status_code == 404


def test_a_campaign_posted_the_way_the_panel_posts_it(client, auth):
    """The exact 500 the live panel was throwing on every campaign.

    `Lang` is `dict[str, str] | str`, and the template-wrapping code read it as
    `payload.body.en`. The panel always sends the dict, so creating a campaign
    from the UI failed with `'dict' object has no attribute 'en'` — while the
    tests, which mostly posted plain strings, stayed green.
    """
    r = client.post("/api/campaigns", headers=auth, json={
        "name": {"en": "Bilingual", "fa": "دوزبانه"},
        "subject": {"en": "Hello", "fa": "سلام"},
        "body": {"en": "First para\n\nSecond para", "fa": "بند اول\n\nبند دوم"},
    })
    assert r.status_code == 201, r.text
    assert r.json()["name"]["fa"] == "دوزبانه"
    client.delete(f"/api/campaigns/{r.json()['id']}", headers=auth)


def test_the_send_time_recommendation_is_actually_reachable(client, auth):
    """It was shadowed by `/{campaign_id}` and answered 404 to everyone."""
    r = client.get("/api/campaigns/best-time", headers=auth)
    assert r.status_code == 200, r.text
    assert "at" in r.json()


def test_a_campaign_without_an_audience_cannot_send(client, auth):
    cid = client.post("/api/campaigns", headers=auth,
                      json={"name": "No audience"}).json()["id"]
    r = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
    assert r.status_code == 422
    client.delete(f"/api/campaigns/{cid}", headers=auth)


def test_unknown_body_fields_are_rejected(client, auth):
    r = client.post("/api/campaigns", headers=auth, json={"name": "x", "titel": "typo"})
    assert r.status_code == 422
    assert "problems" in r.json()


# ================================================================ audience


def test_contact_crud_and_suppression_stay_consistent(client, auth):
    made = client.post("/api/contacts", headers=auth, json={
        "email": "TestPerson@example.com", "name": {"en": "Test Person", "fa": "شخص آزمایشی"},
        "tags": ["beta"],
    })
    assert made.status_code == 201, made.text
    cid = made.json()["id"]
    assert made.json()["email"] == "testperson@example.com"  # normalised

    # unsubscribing must also land on the suppression list
    client.patch(f"/api/contacts/{cid}", headers=auth, json={"status": "unsubscribed"})
    supp = client.get("/api/suppression?q=testperson", headers=auth).json()
    assert supp["total"] == 1

    # …and re-subscribing must remove it again
    client.patch(f"/api/contacts/{cid}", headers=auth, json={"status": "subscribed"})
    assert client.get("/api/suppression?q=testperson", headers=auth).json()["total"] == 0

    client.delete(f"/api/contacts/{cid}", headers=auth)


def test_a_duplicate_contact_is_a_conflict(client, auth):
    payload = {"email": "dupe@example.com"}
    first = client.post("/api/contacts", headers=auth, json=payload)
    assert first.status_code == 201
    assert client.post("/api/contacts", headers=auth, json=payload).status_code == 409
    client.delete(f"/api/contacts/{first.json()['id']}", headers=auth)


def test_csv_import_reports_per_row_outcomes(client, auth):
    csv = "email,name,tags\nnew1@example.com,New One,alpha|beta\nbroken-address,Bad,\nnew2@example.com,New Two,\n"
    r = client.post("/api/contacts/import", headers=auth, json={"csv": csv, "default_tags": ["import"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2
    assert body["error_count"] == 1
    assert body["errors"][0]["line"] == 3

    for email in ("new1@example.com", "new2@example.com"):
        found = client.get(f"/api/contacts?q={email}", headers=auth).json()
        assert found["total"] == 1
        client.delete(f"/api/contacts/{found['items'][0]['id']}", headers=auth)


def test_import_refuses_a_file_without_an_email_column(client, auth):
    r = client.post("/api/contacts/import", headers=auth, json={"csv": "name,age\nBob,4\n"})
    assert r.status_code == 422


def test_a_suppressed_address_cannot_be_re_added(client, auth):
    client.post("/api/suppression", headers=auth, json={"email": "blocked@example.com", "reason": "complaint"})
    r = client.post("/api/contacts", headers=auth, json={"email": "blocked@example.com"})
    assert r.status_code == 409


def test_segment_preview_runs_the_rules_against_real_contacts(client, auth):
    r = client.get("/api/segments/vip/preview", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "total" in body and isinstance(body["items"], list)


def test_segment_rules_cannot_name_an_arbitrary_column(client, auth):
    """An unknown field is REFUSED, not quietly dropped.

    This used to assert the opposite: that the rule was dropped and the segment
    saved with a size equal to the whole contact list. The column never reached
    SQL either way — that part was always right — but "every rule fell out"
    compiled to `WHERE 1=1`, so a segment meant to describe a few hundred
    people silently described all of them, and the next campaign aimed at it
    went to everybody.
    """
    made = client.post("/api/segments", headers=auth, json={
        "name": "Injection attempt",
        "rules": [{"field": "password_hash", "op": "eq", "value": "x"}],
    })
    assert made.status_code == 422
    assert "password_hash" in made.json()["detail"]


def test_a_typo_in_one_rule_does_not_widen_a_segment_to_everyone(client, auth):
    """The realistic version of the same bug: a valid rule beside a mistyped one."""
    made = client.post("/api/segments", headers=auth, json={
        "name": "Big spenders",
        "rules": [
            {"field": "ltv", "op": "gte", "value": "500"},
            {"field": "totalSpent", "op": "gte", "value": "500"},   # not a real field
        ],
    })
    assert made.status_code == 422
    assert "totalSpent" in made.json()["detail"]


def test_a_segment_with_no_rules_must_say_it_means_everyone(client, auth):
    """The old rule tried to distinguish "explicitly empty" from "accidentally
    empty". It could not: both arrive as `rules: []`, byte for byte, so the
    distinction lived only in a comment and the accident went through — a group
    someone forgot to describe silently matched the whole contact table.

    Targeting everyone is still allowed. It has to be said out loud.
    """
    forgot = client.post("/api/segments", headers=auth, json={"name": "Oops", "rules": []})
    assert forgot.status_code == 422
    assert "everyone" in forgot.json()["detail"].lower()

    meant = client.post("/api/segments", headers=auth,
                        json={"name": "Everyone", "rules": [], "match": "everyone"})
    assert meant.status_code == 201, meant.text
    # "Everyone" means everyone we may actually mail — subscribed contacts.
    # Not the row count: someone who unsubscribed is still a contact, and a
    # group sitting next to a send button that counts them is making a promise
    # about the send that the send will not keep.
    stats = client.get("/api/contacts/stats", headers=auth).json()
    assert meant.json()["size"] == stats["subscribed"]
    assert stats["subscribed"] < stats["total"], "fixture should have some unsubscribed"
    client.delete(f"/api/segments/{meant.json()['id']}", headers=auth)


def test_a_segment_in_use_cannot_be_deleted(client, auth):
    assert client.delete("/api/segments/vip", headers=auth).status_code == 409


# ================================================================ agents


def test_agents_list_and_trace(client, auth):
    agents = client.get("/api/agents", headers=auth).json()
    assert len(agents) >= 5
    detail = client.get("/api/agents/nova", headers=auth).json()
    assert detail["name"]["fa"] == "نووا"
    assert len(detail["trace"]) >= 4


def test_pausing_an_agent_changes_its_state(client, auth):
    client.post("/api/agents/echo/pause", headers=auth)
    assert client.get("/api/agents/echo", headers=auth).json()["status"] == "paused"
    client.post("/api/agents/echo/resume", headers=auth)
    assert client.get("/api/agents/echo", headers=auth).json()["status"] == "active"


def test_an_agent_cannot_be_given_a_tool_that_does_not_exist(client, auth):
    r = client.patch("/api/agents/nova", headers=auth, json={"tools": ["contacts.read", "launch.missiles"]})
    assert r.status_code == 422
    assert "launch.missiles" in r.json()["detail"]


def test_a_paused_agent_refuses_to_compose(client, auth):
    client.post("/api/agents/vega/pause", headers=auth)
    r = client.post("/api/ai/compose", headers=auth, json={"brief": "hi", "agent": "vega"})
    assert r.status_code == 409


# ================================================================ inbox


def test_inbox_filters_and_counts(client, auth):
    body = client.get("/api/inbox?filter=needs", headers=auth).json()
    assert all(t["handled"] is False for t in body["items"])
    assert body["counts"]["needs"] >= 1


def test_approving_an_optout_reply_suppresses_the_address(client, auth):
    thread = client.get("/api/inbox/t-3", headers=auth).json()
    client.post("/api/inbox/t-3/reply", headers=auth, json={"send": True})
    supp = client.get(f"/api/suppression?q={thread['email'].split('@')[0]}", headers=auth).json()
    assert supp["total"] >= 1


# ================================================================ experiments


def test_an_experiment_below_threshold_cannot_be_promoted(client, auth):
    r = client.post("/api/experiments/x-3/promote", headers=auth)   # 64.2% confidence
    assert r.status_code == 409
    assert "95%" in r.json()["detail"]


def test_a_confident_experiment_promotes_its_best_variant(client, auth):
    r = client.post("/api/experiments/x-2/promote", headers=auth)   # 99.1%
    assert r.status_code == 200
    winners = [v for v in r.json()["variants"] if v["winner"]]
    assert len(winners) == 1
    assert winners[0]["rate"] == max(v["rate"] for v in r.json()["variants"])


# ================================================================ journeys


def test_a_journey_needs_a_step_before_it_can_run(client, auth):
    made = client.post("/api/journeys", headers=auth,
                       json={"name": "Empty", "trigger": "Nothing"}).json()
    assert client.post(f"/api/journeys/{made['id']}/resume", headers=auth).status_code == 409

    client.post(f"/api/journeys/{made['id']}/steps", headers=auth,
                json={"type": "email", "label": {"en": "Hello", "fa": "سلام"}})
    assert client.post(f"/api/journeys/{made['id']}/resume", headers=auth).json()["status"] == "active"


def test_steps_keep_a_contiguous_order(client, auth):
    jid = client.get("/api/journeys", headers=auth).json()[0]["id"]
    before = client.get(f"/api/journeys/{jid}", headers=auth).json()["steps"]
    client.post(f"/api/journeys/{jid}/steps", headers=auth,
                json={"type": "wait", "label": "Inserted", "position": 1})
    after = client.get(f"/api/journeys/{jid}", headers=auth).json()["steps"]
    assert len(after) == len(before) + 1
    assert after[1]["label"]["en"] == "Inserted"


# ================================================================ analytics


def test_overview_and_series(client, auth):
    body = client.get("/api/stats/overview", headers=auth).json()
    assert body["totals"]["sent"] > 0
    assert 0 <= body["totals"]["openRate"] <= 100

    series = client.get("/api/stats/series?range=30", headers=auth).json()
    assert len(series["labels"]) == 30
    assert len(series["series"][0]["data"]) == 30


def test_heatmap_shape_and_best_slot(client, auth):
    body = client.get("/api/stats/heatmap", headers=auth).json()
    assert len(body["values"]) == 7 and len(body["values"][0]) == 12
    assert 0 <= body["best"]["weekday"] < 7


def test_breakdown_switches_dimension(client, auth):
    for dim in ("campaign", "segment", "agent", "device"):
        r = client.get(f"/api/stats/breakdown?dim={dim}", headers=auth)
        assert r.status_code == 200, dim
        assert isinstance(r.json(), list)


def test_breakdown_rejects_an_unknown_dimension(client, auth):
    assert client.get("/api/stats/breakdown?dim=colour", headers=auth).status_code == 422


def test_deliverability_flags_the_unsigned_domain(client, auth):
    body = client.get("/api/deliverability", headers=auth).json()
    assert any("DKIM" in i["text"]["en"] for i in body["issues"])


# ================================================================ ai


def test_compose_returns_a_draft_and_charges_credits(client, auth):
    before = client.get("/api/billing", headers=auth).json()["usage"]["credits"]["used"]
    r = client.post("/api/ai/compose", headers=auth,
                    json={"brief": "Announce the sale", "tone": "urgent", "lang": "en"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subject"] and len(body["body"]) >= 2
    assert len(body["suggestions"]) == 4
    after = client.get("/api/billing", headers=auth).json()["usage"]["credits"]["used"]
    assert after == before + body["creditsCharged"]


def test_compose_honours_language_and_length(client, auth):
    fa = client.post("/api/ai/compose", headers=auth,
                     json={"lang": "fa", "tone": "friendly", "length": "short"}).json()
    assert len(fa["body"]) == 2
    # Persian output must actually be Persian
    assert any("؀" <= ch <= "ۿ" for ch in fa["subject"])


def test_compose_enforces_the_banned_word_list(client, auth):
    client.patch("/api/knowledge/voice", headers=auth, json={"banned": ["summer"]})
    body = client.post("/api/ai/compose", headers=auth, json={"lang": "en"}).json()
    assert "summer" in body["analysis"]["guardrailViolations"]
    client.patch("/api/knowledge/voice", headers=auth, json={"banned": []})


def test_segment_builder_compiles_a_sentence_into_rules(client, auth):
    r = client.post("/api/ai/segment", headers=auth,
                    json={"prompt": "people who bought 2 times but have not opened in 90 days"})
    assert r.status_code == 200, r.text
    body = r.json()
    rules = {rule["field"]: rule for rule in body["rules"]}
    assert set(rules) >= {"orders", "lastOpen"}
    # each number must bind to ITS OWN unit, not to whichever came first
    assert rules["orders"]["value"] == "2"
    assert rules["lastOpen"]["value"] == "90d"
    assert body["preview"]["matched"] <= body["preview"]["total"]


def test_segment_builder_reads_persian_numbers_and_units(client, auth):
    r = client.post("/api/ai/segment", headers=auth,
                    json={"prompt": "کسانی که 3 بار سفارش داده‌اند و 60 روز باز نکرده‌اند"})
    assert r.status_code == 200, r.text
    rules = {rule["field"]: rule for rule in r.json()["rules"]}
    assert rules["orders"]["value"] == "3"
    assert rules["lastOpen"]["value"] == "60d"


def test_segment_builder_needs_a_prompt(client, auth):
    assert client.post("/api/ai/segment", headers=auth, json={"prompt": "   "}).status_code == 422


# ================================================================ workspace


def test_a_workspace_must_keep_an_owner(client, auth):
    r = client.patch("/api/team/u-1", headers=auth, json={"role": "viewer"})
    assert r.status_code == 409


def test_you_cannot_remove_yourself(client, auth):
    assert client.delete("/api/team/u-1", headers=auth).status_code == 409


def test_settings_round_trip(client, auth):
    client.patch("/api/settings", headers=auth, json={"from_name": "Acme Team", "creativity": 42})
    body = client.get("/api/settings", headers=auth).json()
    assert body["sending"]["fromName"] == "Acme Team"
    assert body["ai"]["creativity"] == 42


def test_a_domain_must_look_like_a_domain(client, auth):
    assert client.post("/api/domains", headers=auth, json={"domain": "not a domain"}).status_code == 422


def test_a_domain_that_authenticates_is_verified(client, auth, monkeypatch):
    """The happy path, with the lookups faked at the DNS boundary."""
    from app import dnscheck

    made = client.post("/api/domains", headers=auth, json={"domain": "send.example.com"}).json()
    assert made["status"] == "unverified"
    assert all(not r["ok"] for r in made["records"])

    monkeypatch.setattr(dnscheck, "check",
                        lambda d: {"spf": "pass", "dkim": "pass", "dmarc": "pass"})
    verified = client.post(f"/api/domains/{made['id']}/verify", headers=auth).json()
    assert verified["status"] == "verified"


def test_verification_never_fabricates_a_pass(client, auth, monkeypatch):
    """The reason this route was rewritten.

    It used to write spf=1, dkim=1, dmarc=1 and tick every DNS record
    WITHOUT RESOLVING ANYTHING, so the screen a customer checks before a
    large send showed three green ticks for a domain with no SPF record at
    all. A lookup that cannot answer must leave the domain unverified.
    """
    from app import dnscheck, senderhealth

    made = client.post("/api/domains", headers=auth, json={"domain": "unreachable.example"}).json()
    monkeypatch.setattr(dnscheck, "check",
                        lambda d: {"spf": "unknown", "dkim": "unknown", "dmarc": "unknown"})

    after = client.post(f"/api/domains/{made['id']}/verify", headers=auth).json()
    assert after["status"] == "unverified"
    assert all(not r["ok"] for r in after["records"])

    # and the health readout says unknown rather than claiming a failure:
    # "we could not check" and "there is no record" are different answers
    row = db.one("SELECT * FROM domains WHERE id = ?", (made["id"],))
    assert row["spf_state"] == "unknown"


def test_a_missing_spf_record_is_a_failure_not_an_unknown(client, auth, monkeypatch):
    """The other half: an answer of "there is nothing there" is a fail."""
    from app import dnscheck

    made = client.post("/api/domains", headers=auth, json={"domain": "nospf.example"}).json()
    monkeypatch.setattr(dnscheck, "check",
                        lambda d: {"spf": "fail", "dkim": "unknown", "dmarc": "fail"})
    client.post(f"/api/domains/{made['id']}/verify", headers=auth)

    row = db.one("SELECT * FROM domains WHERE id = ?", (made["id"],))
    assert row["spf_state"] == "fail"
    assert row["spf"] == 0


def test_webhooks_must_be_https_and_use_known_events(client, auth):
    assert client.post("/api/webhooks", headers=auth,
                       json={"url": "http://insecure.example.com"}).status_code == 422
    assert client.post("/api/webhooks", headers=auth,
                       json={"url": "https://ok.example.com",
                             "events": ["email.exploded"]}).status_code == 422


# ================================================================ api keys


def test_an_api_key_is_shown_once_and_then_only_hashed(client, auth):
    made = client.post("/api/api-keys", headers=auth,
                       json={"name": "CI", "scopes": ["analytics:read"]})
    assert made.status_code == 201
    token = made.json()["token"]
    assert token.startswith("mp_live_")

    listed = client.get("/api/api-keys", headers=auth).json()
    mine = next(k for k in listed if k["id"] == made.json()["id"])
    assert "token" not in mine

    # the key authenticates, within its scope
    ok = client.get("/api/stats/overview", headers={"X-API-Key": token})
    assert ok.status_code == 200

    # …and is refused outside it
    denied = client.post("/api/campaigns", headers={"X-API-Key": token}, json={"name": "nope"})
    assert denied.status_code == 403

    # a key may never do a human-only action
    human_only = client.get("/api/team", headers={"X-API-Key": token})
    assert human_only.status_code == 403


def test_a_bogus_api_key_is_refused(client):
    assert client.get("/api/stats/overview", headers={"X-API-Key": "mp_live_nope"}).status_code == 401


# ================================================================ misc


def test_activity_log_records_mutations(client, auth):
    before = client.get("/api/activity", headers=auth).json()["total"]
    cid = client.post("/api/campaigns", headers=auth, json={"name": "Logged"}).json()["id"]
    after = client.get("/api/activity", headers=auth).json()["total"]
    assert after > before
    client.delete(f"/api/campaigns/{cid}", headers=auth)


def test_notifications_can_be_marked_read(client, auth):
    assert client.get("/api/notifications", headers=auth).json()["unread"] >= 1
    client.post("/api/notifications/read", headers=auth)
    assert client.get("/api/notifications", headers=auth).json()["unread"] == 0


def test_every_response_carries_a_request_id(client, auth):
    r = client.get("/api/health")
    assert r.headers.get("X-Request-Id")


def test_search_wildcards_are_escaped(client, auth):
    """A "%" in the query must be a literal, not "match everything".

    Exactly one seeded campaign has a percent sign in its subject
    ("A quiet 20% while you decide"), so a working escape returns that one.
    An unescaped wildcard would return every campaign instead.
    """
    total = client.get("/api/campaigns", headers=auth).json()["total"]
    body = client.get("/api/campaigns?q=%25", headers=auth).json()
    assert body["total"] == 1
    assert body["total"] < total
    assert "%" in body["items"][0]["subject"]["en"]


# ================================================== the email finder's groups


def _seed_a_finder_run(email: str = "hello@zargar-dubai.example"):
    """A finished search with one lead on it, written straight to the tables.

    The search itself is an AI call over web results, which does not belong in
    a test — what is being tested is what happens to leads once a person has
    accepted them.
    """
    from app.domain import iso
    from app.security import new_id

    run_id = new_id("run")
    lead_id = new_id("ld")
    with db.transaction():
        db.insert("lead_runs", {
            "id": run_id, "region": "Dubai", "category": "gold shops",
            "brief": "", "angles": "[]", "found": 1, "with_email": 1,
            "created_at": iso(),
        })
        db.insert("leads", {
            "id": lead_id, "name": "Zargar Dubai", "kind": "gold shop",
            "region": "Dubai", "email": email,
            "website": "https://zargar-dubai.example",
            "source": "https://zargar-dubai.example/contact",
            "note": "", "status": "new", "run_id": run_id, "created_at": iso(),
        })
    return lead_id


def test_accepted_leads_are_tagged_and_grouped_by_the_search(client, auth):
    """A batch of found addresses has to arrive selectable.

    Accepting used to drop them loose into the contact list with whatever
    tags the caller happened to pass, which in practice was none — so twenty
    gold shops from Dubai became twenty rows indistinguishable from every
    other contact, and there was no way to send to just them.
    """
    lead = _seed_a_finder_run()
    r = client.post("/api/research/leads/accept", headers=auth, json={"ids": [lead]})
    assert r.status_code == 200, r.text
    out = r.json()

    assert out["added"] == 1
    assert out["tag"] == "gold shops Dubai"
    assert out["group"] == "gold shops Dubai"

    # the group exists, and its rule is the tag the contacts carry
    groups = client.get("/api/segments", headers=auth).json()
    made = [g for g in groups if g["name"]["en"] == "gold shops Dubai"]
    assert len(made) == 1

    # and the rule actually resolves to the contact that was just accepted --
    # a group that exists but matches nobody would be worse than no group
    seen = client.get(f"/api/segments/{made[0]['id']}/preview", headers=auth)
    assert seen.status_code == 200, seen.text
    assert any(m["email"] == "hello@zargar-dubai.example" for m in seen.json()["items"])


def test_running_the_same_search_twice_widens_one_group(client, auth):
    """Not two groups with the same name beside each other.

    Self-contained rather than leaning on the test above: a test that only
    passes when its neighbour ran first fails for reasons that have nothing
    to do with the code.
    """
    client.post("/api/research/leads/accept", headers=auth,
                json={"ids": [_seed_a_finder_run("first@zargar-dubai.example")]})
    client.post("/api/research/leads/accept", headers=auth,
                json={"ids": [_seed_a_finder_run("second@zargar-dubai.example")]})

    made = [g for g in client.get("/api/segments", headers=auth).json()
            if g["name"]["en"] == "gold shops Dubai"]
    assert len(made) == 1


# ============================================ approving a reply actually sends


def test_approving_a_reply_sends_it_over_gmail(client, auth, monkeypatch):
    """The whole point of the button, and it had no test at all.

    That is how the route shipped marking threads handled, counting a
    'replied' event and writing 'approved and sent an agent reply' into the
    activity log without ever contacting Gmail. Nothing caught it because
    nothing asked whether a message went out.

    Gmail is faked at the transport boundary only — everything above it, the
    threading headers, the subject, the recipient and the MIME build, is the
    real code.
    """
    from app import google, mailer

    _connect_a_mailbox()
    sent: list[dict] = []

    monkeypatch.setattr(mailer, "access_token", lambda: "fake-access-token")
    monkeypatch.setattr(google, "read_message", lambda tok, mid: {
        "id": mid, "threadId": "thread-abc",
        "messageId": "<original@mail.example>", "references": "",
        "from": "Ali <ali@example.com>", "subject": "A question",
        "snippet": "", "body": "", "at": 0,
    })
    monkeypatch.setattr(google, "send_message",
                        lambda tok, raw, thread_id="": sent.append({"raw": raw, "thread": thread_id})
                        or {"id": "sent-1"})

    thread = client.get("/api/inbox/t-1", headers=auth).json()
    r = client.post("/api/inbox/t-1/reply", headers=auth,
                    json={"send": True, "text": {"en": "Thanks, here you go.",
                                                 "fa": "ممنون، بفرمایید."}})
    assert r.status_code == 200, r.text

    # something actually went out
    assert len(sent) == 1, "approving a reply must reach Gmail"

    import base64
    raw = base64.urlsafe_b64decode(sent[0]["raw"]).decode("utf-8", "replace")
    # threaded, or it arrives as a loose message with Re: on it
    assert sent[0]["thread"] == "thread-abc"
    assert "In-Reply-To: <original@mail.example>" in raw
    assert "Re:" in raw
    assert thread["email"] in raw
    assert "Thanks, here you go." in raw

    # and only now is the thread handled
    assert client.get("/api/inbox/t-1", headers=auth).json()["handled"] is True


def test_a_reply_that_gmail_refuses_is_not_marked_handled(client, auth, monkeypatch):
    """A failed send must not look like a successful one.

    The old route marked the thread handled and logged a send unconditionally,
    so an operator had no way to tell a delivered reply from one that never
    left the building.
    """
    from app import google, mailer

    _connect_a_mailbox()
    monkeypatch.setattr(mailer, "access_token", lambda: "fake-access-token")
    monkeypatch.setattr(google, "read_message", lambda tok, mid: {
        "id": mid, "threadId": "t", "messageId": "<x@y>", "references": "",
        "from": "a@b.c", "subject": "s", "snippet": "", "body": "", "at": 0,
    })

    def refuse(tok, raw, thread_id=""):
        raise google.GoogleError("Gmail said no")

    monkeypatch.setattr(google, "send_message", refuse)

    r = client.post("/api/inbox/t-2/reply", headers=auth,
                    json={"send": True, "text": {"en": "hello", "fa": "سلام"}})
    assert r.status_code == 502
    assert "Gmail said no" in r.json()["detail"]
    assert client.get("/api/inbox/t-2", headers=auth).json()["handled"] is False


def test_an_empty_draft_is_refused_before_gmail(client, auth):
    """Sending an empty email is worse than sending nothing."""
    from app import db

    db.execute("UPDATE threads SET draft_en = '', draft_fa = '' WHERE id = 't-4'")
    r = client.post("/api/inbox/t-4/reply", headers=auth, json={"send": True})
    assert r.status_code == 422
