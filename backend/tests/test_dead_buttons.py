"""The failures that made whole screens look broken.

Every one of these was reported as "the buttons don't work". None of them was
a button: one was a 500 that killed campaign creation, one was a route that
answered 404 to everyone, and one was an endpoint that never existed because
the control in front of it had no handler.

They share a shape worth naming — a request that is WRONG being answered as
though the server were BROKEN. A 500 tells the operator nothing they can act
on, so they conclude the feature is dead and stop using it.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-buttons-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"
os.environ["MAILPILOT_SENDER"] = "0"

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
    r = client.post("/api/auth/login",
                    json={"email": "pouya@acme.io", "password": "mailpilot"})
    # A reply-to, because a send with no way to unsubscribe is now refused —
    # see `_check_ready`. Every real deployment has one; the empty fixture did
    # not, which is exactly the state that check exists to catch.
    db.update("deployment", "1", {"reply_to": "replies@example.com"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# =========================================== a bad id is not a broken server


def test_a_segment_that_does_not_exist_is_a_422_not_a_500(client, auth):
    """The one that killed the campaign screen.

    Nothing validated the id, so the insert reached SQLite, tripped a FOREIGN
    KEY constraint, and surfaced as "Internal Server Error". A fresh install
    has no segments at all, so this was the first thing a new customer hit —
    and with creation dead, edit, send-now and send-later all looked dead too.
    """
    r = client.post("/api/campaigns", headers=auth, json={
        "name": "X", "subject": "S", "body": "B", "segment": "does-not-exist",
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "does-not-exist" in detail      # names the offending value
    assert "audience" in detail.lower()    # in words the operator uses


def test_an_agent_that_does_not_exist_is_refused_the_same_way(client, auth):
    r = client.post("/api/campaigns", headers=auth,
                    json={"name": "X", "agent": "no-such-agent"})
    assert r.status_code == 422


def test_editing_onto_a_bad_id_is_refused_too(client, auth):
    """PATCH had the same hole as POST."""
    cid = client.post("/api/campaigns", headers=auth, json={"name": "Patchable"}).json()["id"]
    r = client.patch(f"/api/campaigns/{cid}", headers=auth, json={"segment": "invented"})
    assert r.status_code == 422
    client.delete(f"/api/campaigns/{cid}", headers=auth)


def test_a_campaign_with_no_audience_at_all_is_still_allowed(client, auth):
    """A draft before you know who it is for is a normal thing to write."""
    r = client.post("/api/campaigns", headers=auth,
                    json={"name": {"en": "No audience yet", "fa": "بدون مخاطب"}})
    assert r.status_code == 201, r.text
    client.delete(f"/api/campaigns/{r.json()['id']}", headers=auth)


# ================================================ a route hidden by a wildcard


def test_best_time_is_reachable(client, auth):
    """It is declared before `/{campaign_id}` and must stay there.

    Below the wildcard, FastAPI reads the path as a campaign named "best-time"
    and answers 404 — to everyone, forever. The send-later button asks this for
    a recommendation and got a 404 every time.
    """
    r = client.get("/api/campaigns/best-time", headers=auth)
    assert r.status_code == 200, r.text
    assert "at" in r.json()


# ============================================== the group button did nothing


def test_tagging_several_people_at_once(client, auth):
    """"Add to a group" in a product where a group is a rule.

    There is no membership list to append to — a segment is re-evaluated on
    every read. Tagging is the thing a person can actually do, and it is what
    the rule then matches.
    """
    made = [client.post("/api/contacts", headers=auth,
                        json={"email": f"bulk{i}@example.com", "name": f"B{i}"})
            for i in range(3)]
    ids = [r.json()["id"] for r in made if r.status_code == 201]
    assert len(ids) == 3

    r = client.post("/api/contacts/bulk/tag", headers=auth,
                    json={"ids": ids, "addTags": ["vip"]})
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 3

    row = db.one("SELECT tags FROM contacts WHERE id = ?", (ids[0],))
    assert "vip" in db.loads(row["tags"], [])


def test_tagging_twice_does_not_duplicate_the_tag(client, auth):
    cid = client.post("/api/contacts", headers=auth,
                      json={"email": "twice@example.com"}).json()["id"]
    for _ in range(2):
        client.post("/api/contacts/bulk/tag", headers=auth,
                    json={"ids": [cid], "addTags": ["vip"]})
    tags = db.loads(db.one("SELECT tags FROM contacts WHERE id = ?", (cid,))["tags"], [])
    assert tags.count("vip") == 1


def test_a_tag_can_be_taken_off_again(client, auth):
    cid = client.post("/api/contacts", headers=auth,
                      json={"email": "removable@example.com", "tags": ["vip", "keep"]}).json()["id"]
    client.post("/api/contacts/bulk/tag", headers=auth,
                json={"ids": [cid], "removeTags": ["vip"]})
    tags = db.loads(db.one("SELECT tags FROM contacts WHERE id = ?", (cid,))["tags"], [])
    assert tags == ["keep"]


def test_tagging_nothing_is_refused_rather_than_silently_doing_nothing(client, auth):
    assert client.post("/api/contacts/bulk/tag", headers=auth,
                       json={"ids": [], "addTags": ["vip"]}).status_code == 422
    assert client.post("/api/contacts/bulk/tag", headers=auth,
                       json={"ids": ["p-1"], "addTags": []}).status_code == 422


def test_a_tag_puts_people_into_the_group_that_looks_for_it(client, auth):
    """The whole point, end to end."""
    seg = client.post("/api/segments", headers=auth, json={
        "name": {"en": "Tagged VIPs", "fa": "ویژه‌ها"},
        "rules": [{"field": "tag", "op": "has", "value": "goldmember"}],
    })
    assert seg.status_code == 201, seg.text
    sid = seg.json()["id"]
    assert client.get(f"/api/segments/{sid}/preview", headers=auth).json()["total"] == 0

    cid = client.post("/api/contacts", headers=auth,
                      json={"email": "gold@example.com"}).json()["id"]
    client.post("/api/contacts/bulk/tag", headers=auth,
                json={"ids": [cid], "addTags": ["goldmember"]})

    assert client.get(f"/api/segments/{sid}/preview", headers=auth).json()["total"] == 1
    client.delete(f"/api/segments/{sid}", headers=auth)


def test_deleting_several_at_once(client, auth):
    ids = [client.post("/api/contacts", headers=auth,
                       json={"email": f"gone{i}@example.com"}).json()["id"] for i in range(3)]
    r = client.post("/api/contacts/bulk/delete", headers=auth, json={"ids": ids})
    assert r.status_code == 200 and r.json()["deleted"] == 3
    assert db.one("SELECT 1 FROM contacts WHERE id = ?", (ids[0],)) is None


# ====================================================== nothing hidden by a wildcard


def test_no_literal_route_is_hidden_behind_a_wildcard():
    """FastAPI matches in declaration order, and that has bitten twice.

    `/campaigns/best-time` sat below `/campaigns/{campaign_id}` and answered
    404 to everyone for months. The export routes would have done the same.
    Rather than remembering the rule, this walks the built route table: for
    every literal path, the FIRST route that can match it must be itself.
    """
    from app.main import app

    routes = [
        (r.path, sorted(r.methods or []))
        for r in app.routes
        if getattr(r, "path", "").startswith("/api/") and getattr(r, "methods", None)
    ]

    def can_match(template: str, path: str) -> bool:
        t, p = template.strip("/").split("/"), path.strip("/").split("/")
        if len(t) != len(p):
            return False
        return all(seg.startswith("{") or seg == got for seg, got in zip(t, p))

    hidden = []
    for i, (path, methods) in enumerate(routes):
        if "{" in path:
            continue  # only literal paths can be shadowed
        for earlier_path, earlier_methods in routes[:i]:
            if "{" not in earlier_path:
                continue
            if set(methods) & set(earlier_methods) and can_match(earlier_path, path):
                hidden.append(f"{'/'.join(methods)} {path} is swallowed by {earlier_path}")

    assert not hidden, "unreachable routes:\n  " + "\n  ".join(hidden)


def test_the_export_routes_answer_with_a_spreadsheet(client, auth):
    """They 404'd as "Contact not found" when the wildcard won."""
    for path, first_column in (("/api/contacts/export", "name"),
                               ("/api/campaigns/export", "name"),
                               ("/api/suppression/export", "email")):
        r = client.get(path, headers=auth)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:120]}"
        assert r.headers["content-type"].startswith("text/csv"), path
        assert "attachment" in r.headers.get("content-disposition", ""), path
        body = r.text
        # the BOM Excel needs before it will believe the file is UTF-8
        assert body.startswith("\ufeff"), f"{path} has no BOM"
        assert body.lstrip("\ufeff").startswith(first_column), path


def test_an_export_is_gated_on_being_allowed_to_export(client):
    """Reading one contact and taking the whole list are different rights."""
    from app.domain import PERMISSIONS

    assert "viewer" in PERMISSIONS["contacts.read"]
    assert "viewer" not in PERMISSIONS["contacts.export"]
    assert "analyst" not in PERMISSIONS["contacts.export"]


def test_a_campaign_with_no_sends_has_no_rate_rather_than_zero(client, auth):
    """An empty cell, not 0% — a spreadsheet averages the zero into a chart."""
    from app.exporting import rate

    assert rate(0, 0) == ""
    assert rate(5, 0) == ""
    assert rate(None, None) == ""
    assert rate(25, 100) == 25.0


# ============================================ a mistake must not mean "everyone"


def test_a_send_time_in_the_past_is_refused(client, auth):
    """The most expensive mistake this product can make.

    The worker asks for campaigns whose `scheduled_for <= now`, so a date in
    the past is not scheduled — it is DUE, and goes out on the next tick about
    thirty seconds later. Choosing "send later" and mistyping the year was
    therefore identical to pressing "send now", except nobody meant it.
    """
    seg = client.post("/api/segments", headers=auth, json={
        "name": "Past test", "rules": [{"field": "status", "op": "eq", "value": "subscribed"}],
    }).json()["id"]
    cid = client.post("/api/campaigns", headers=auth, json={
        "name": "Past", "segment": seg, "subject": "Hello", "body": "A real message",
    }).json()["id"]

    r = client.post(f"/api/campaigns/{cid}/send", headers=auth,
                    json={"mode": "schedule", "scheduled_for": "2020-01-01T09:00:00Z"})
    assert r.status_code == 422, r.text
    assert "passed" in r.json()["detail"].lower()

    # and the campaign was not quietly moved to scheduled anyway
    assert client.get(f"/api/campaigns/{cid}", headers=auth).json()["status"] == "draft"

    client.delete(f"/api/campaigns/{cid}", headers=auth)
    client.delete(f"/api/segments/{seg}", headers=auth)


def test_a_future_send_time_is_accepted(client, auth):
    from datetime import datetime, timedelta, timezone

    seg = client.post("/api/segments", headers=auth, json={
        "name": "Future test", "rules": [{"field": "status", "op": "eq", "value": "subscribed"}],
    }).json()["id"]
    cid = client.post("/api/campaigns", headers=auth, json={
        "name": "Future", "segment": seg, "subject": "Hello", "body": "A real message",
    }).json()["id"]

    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.post(f"/api/campaigns/{cid}/send", headers=auth,
                    json={"mode": "schedule", "scheduled_for": when})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduled"

    client.post(f"/api/campaigns/{cid}/pause", headers=auth)
    client.delete(f"/api/campaigns/{cid}", headers=auth)
    client.delete(f"/api/segments/{seg}", headers=auth)


def test_a_send_time_a_minute_old_is_tolerated(client, auth):
    """The browser sends the time IT believes it is. Clock drift is ordinary."""
    from datetime import datetime, timedelta, timezone

    cid = client.post("/api/campaigns", headers=auth, json={"name": "Drift"}).json()["id"]
    just_now = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    r = client.patch(f"/api/campaigns/{cid}", headers=auth,
                     json={"scheduled_for": just_now})
    assert r.status_code == 200, r.text
    client.delete(f"/api/campaigns/{cid}", headers=auth)


def test_an_unreadable_date_says_so(client, auth):
    cid = client.post("/api/campaigns", headers=auth, json={"name": "Junk date"}).json()["id"]
    r = client.patch(f"/api/campaigns/{cid}", headers=auth,
                     json={"scheduled_for": "next tuesday-ish"})
    assert r.status_code == 422
    assert "read" in r.json()["detail"].lower()
    client.delete(f"/api/campaigns/{cid}", headers=auth)


def test_an_empty_campaign_cannot_be_sent(client, auth):
    """A blank email is worse than an error.

    The house template wraps whatever it is handed, so an empty body produces
    a perfectly branded message containing nothing — logo, footer, unsubscribe
    link, and a hole where the words go. Sent to the whole list from the
    customer's own address, that is not a bug the recipient forgives.
    """
    seg = client.post("/api/segments", headers=auth, json={
        "name": "Empty test",
        "rules": [{"field": "status", "op": "eq", "value": "subscribed"}],
    }).json()["id"]

    cid = client.post("/api/campaigns", headers=auth,
                      json={"name": "Nothing in it", "segment": seg,
                            "subject": "Has a subject"}).json()["id"]
    r = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
    assert r.status_code == 422, r.text
    assert "message" in r.json()["detail"].lower()

    # markup and merge tags alone are not content either
    client.patch(f"/api/campaigns/{cid}", headers=auth,
                 json={"body": "<p> </p>{{first_name}}"})
    r = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
    assert r.status_code == 422, "an empty <p> and a merge tag counted as a message"

    client.delete(f"/api/campaigns/{cid}", headers=auth)
    client.delete(f"/api/segments/{seg}", headers=auth)


def test_a_campaign_with_no_subject_cannot_be_sent(client, auth):
    """Mail with no subject line is filtered as spam by most providers."""
    seg = client.post("/api/segments", headers=auth, json={
        "name": "Subjectless test",
        "rules": [{"field": "status", "op": "eq", "value": "subscribed"}],
    }).json()["id"]
    cid = client.post("/api/campaigns", headers=auth,
                      json={"name": "No subject", "segment": seg,
                            "body": "There is a body but no subject."}).json()["id"]

    r = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
    assert r.status_code == 422
    assert "subject" in r.json()["detail"].lower()

    client.delete(f"/api/campaigns/{cid}", headers=auth)
    client.delete(f"/api/segments/{seg}", headers=auth)


def test_a_draft_is_still_allowed_to_be_half_written(client, auth):
    """The check belongs at send, not at save. That is what a draft IS."""
    r = client.post("/api/campaigns", headers=auth, json={"name": "Just a thought"})
    assert r.status_code == 201
    client.delete(f"/api/campaigns/{r.json()['id']}", headers=auth)


# ================================================ a group's size must be true


def test_a_group_size_follows_the_group(client, auth):
    """`segments.size` was written once and never again.

    Tag three more people and the group really does hold three more — the
    stored number started lying the moment anything changed. It was shown on
    the campaign screen next to the send button, which made a wrong count into
    a promise about who was about to be mailed.
    """
    seg = client.post("/api/segments", headers=auth, json={
        "name": "Growing", "rules": [{"field": "tag", "op": "has", "value": "grower"}],
    }).json()
    assert seg["size"] == 0

    cid = client.post("/api/contacts", headers=auth,
                      json={"email": "grower@example.com"}).json()["id"]
    client.post("/api/contacts/bulk/tag", headers=auth,
                json={"ids": [cid], "addTags": ["grower"]})

    listed = [s for s in client.get("/api/segments", headers=auth).json()
              if s["id"] == seg["id"]][0]
    preview = client.get(f"/api/segments/{seg['id']}/preview", headers=auth).json()
    assert listed["size"] == 1, "the list went stale"
    assert listed["size"] == preview["total"], "the list and the preview disagree"

    client.delete(f"/api/segments/{seg['id']}", headers=auth)


def test_a_group_counts_only_people_it_can_actually_mail(client, auth):
    """Someone who unsubscribed is still a contact and is not an audience."""
    seg = client.post("/api/segments", headers=auth, json={
        "name": "Reachable", "rules": [{"field": "tag", "op": "has", "value": "reach"}],
    }).json()["id"]

    stay = client.post("/api/contacts", headers=auth, json={"email": "stay@example.com"}).json()["id"]
    go = client.post("/api/contacts", headers=auth, json={"email": "go@example.com"}).json()["id"]
    client.post("/api/contacts/bulk/tag", headers=auth,
                json={"ids": [stay, go], "addTags": ["reach"]})

    before = [s for s in client.get("/api/segments", headers=auth).json()
              if s["id"] == seg][0]["size"]
    assert before == 2

    client.post("/api/suppression", headers=auth,
                json={"email": "go@example.com", "reason": "unsub"})

    after = [s for s in client.get("/api/segments", headers=auth).json()
             if s["id"] == seg][0]["size"]
    assert after == 1, "an unsubscribed contact still counted toward the audience"

    client.delete(f"/api/segments/{seg}", headers=auth)


# ============================================ research: what must never happen


def test_an_invented_address_is_dropped(client):
    """A model with no address produces one anyway.

    Well-formed, plausible, belonging to nobody — and it hard-bounces. Enough
    bounces get the customer's Gmail account closed, which ends the product for
    them, so this filter is the most important line in the feature.
    """
    from app import prospect

    real = prospect.clean_email("hello@northwind.ir", "https://northwind.ir/contact")
    assert real == "hello@northwind.ir"

    # the placeholder domains every model reaches for
    for junk in ("info@example.com", "hello@yourcompany.com", "a@acme.com",
                 "x@test.com", "b@domain.example"):
        assert prospect.clean_email(junk, "https://real.ir/page") == "", junk

    # and an address with no citation is an address nobody read
    assert prospect.clean_email("real@northwind.ir", "") == ""
    assert prospect.clean_email("real@northwind.ir", "   ") == ""


def test_a_lead_without_a_source_is_not_stored(client):
    """No citation, no lead — the rule the whole feature rests on."""
    from app import db, prospect

    out = prospect.store("run-test-1", "Tehran", "cafes", {
        "brief": "b", "angles": [],
        "leads": [
            {"name": "Cited", "email": "a@cited.ir", "source": "https://cited.ir/x"},
            {"name": "Uncited", "email": "b@uncited.ir"},
            {"name": "Also uncited", "email": "c@x.ir", "source": "  "},
        ],
    })
    assert out["found"] == 1
    assert out["droppedWithoutSource"] == 2
    rows = db.query("SELECT name FROM leads WHERE run_id = 'run-test-1'")
    assert [r["name"] for r in rows] == ["Cited"]


def test_research_never_writes_a_contact_on_its_own(client, auth):
    """Finding is not consent. Only an explicit accept adds anybody."""
    from app import db, prospect

    before = db.scalar("SELECT COUNT(*) FROM contacts", default=0)
    prospect.store("run-test-2", "Tehran", "cafes", {
        "brief": "b", "angles": [],
        "leads": [{"name": "Somewhere", "email": "pick@somewhere.ir",
                   "source": "https://somewhere.ir"}],
    })
    assert db.scalar("SELECT COUNT(*) FROM contacts", default=0) == before

    lead = db.one("SELECT id FROM leads WHERE run_id = 'run-test-2'")
    r = client.post("/api/research/leads/accept", headers=auth, json={"ids": [lead["id"]]})
    assert r.status_code == 200 and r.json()["added"] == 1
    assert db.scalar("SELECT COUNT(*) FROM contacts", default=0) == before + 1

    # and the citation survives onto the contact record
    row = db.one("SELECT source_en FROM contacts WHERE email = 'pick@somewhere.ir'")
    assert "somewhere.ir" in row["source_en"]


def test_accepting_a_lead_still_obeys_the_blocked_list(client, auth):
    """A researched lead has earned no exemption from an unsubscribe."""
    from app import db, prospect

    client.post("/api/suppression", headers=auth,
                json={"email": "nope@blocked.ir", "reason": "unsub"})
    prospect.store("run-test-3", "Tehran", "cafes", {
        "brief": "b", "angles": [],
        "leads": [{"name": "Blocked", "email": "nope@blocked.ir",
                   "source": "https://blocked.ir"}],
    })
    lead = db.one("SELECT id FROM leads WHERE run_id = 'run-test-3'")
    out = client.post("/api/research/leads/accept", headers=auth,
                      json={"ids": [lead["id"]]}).json()
    assert out["added"] == 0 and out["refusedAsUnsubscribed"] == 1
    assert db.one("SELECT 1 FROM contacts WHERE email = 'nope@blocked.ir'") is None


def test_research_refuses_to_run_without_web_search(client, auth):
    """Answering from memory means inventing businesses that never existed."""
    from app import db, deployment

    db.update("deployment", "1", {"ai_key": "sk-test", "ai_search": 0})
    try:
        r = client.post("/api/research/run", headers=auth,
                        json={"region": "Tehran", "category": "cafes"})
        assert r.status_code == 400
        assert "search" in r.json()["detail"].lower()
    finally:
        db.update("deployment", "1", {"ai_key": "", "ai_search": 1})


def test_research_needs_both_inputs(client, auth):
    for body in ({"region": "Tehran"}, {"category": "cafes"}, {}):
        r = client.post("/api/research/run", headers=auth, json=body)
        assert r.status_code == 422, body


# ====================================== a fresh install must be able to send


def test_an_install_always_has_an_audience(client, auth):
    """Production had eight drafts, no groups, and an empty outbox.

    Every group is a rule, so the first one cannot derive itself from the data
    — and without one the product cannot send at all. The agent had nothing to
    point a campaign at, the campaign was created with no audience, and the
    send was refused. The operator retried, which is why the same subject
    appears three times seconds apart in the real database.
    """
    from app import db
    from app.seed import ensure_default_segment

    db.execute("DELETE FROM campaigns WHERE segment_id IS NOT NULL")
    db.execute("DELETE FROM segments")
    assert ensure_default_segment() is True

    groups = client.get("/api/segments", headers=auth).json()
    assert len(groups) == 1
    everyone = groups[0]
    assert everyone["match"] == "everyone"
    # and it really does hold the reachable contacts
    stats = client.get("/api/contacts/stats", headers=auth).json()
    assert everyone["size"] == stats["subscribed"]


def test_it_never_overwrites_groups_that_already_exist(client, auth):
    from app.seed import ensure_default_segment

    assert ensure_default_segment() is False, "it created a second one"


def test_a_campaign_can_actually_be_sent_on_a_fresh_install(client, auth):
    """The whole chain, from nothing to queued."""
    from app import db, deployment, mailer
    from app.seed import ensure_default_segment

    ensure_default_segment()
    everyone = client.get("/api/segments", headers=auth).json()[0]["id"]

    cid = client.post("/api/campaigns", headers=auth, json={
        "name": "First send", "subject": "Hello", "body": "A real message.",
        "segment": everyone,
    }).json()["id"]

    deployment.save_google(google_refresh="fake", google_email="a@b.c")
    try:
        r = client.post(f"/api/campaigns/{cid}/send", headers=auth, json={"mode": "now"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "running"
        # and the outbox is no longer empty, which is what production was missing
        assert mailer.progress(cid)["queued"] > 0
    finally:
        deployment.save_google(google_refresh="", google_email="")
        db.execute("DELETE FROM outbox WHERE campaign_id = ?", (cid,))
        client.delete(f"/api/campaigns/{cid}", headers=auth)


def test_the_agent_can_build_an_audience_when_none_exists(client):
    """It could name a segment id and never make one."""
    from app import db, tools

    db.execute("DELETE FROM segments WHERE name_en = 'Agent made'")
    out = tools.run("create_group", {
        "name": "Agent made", "match": "everyone", "rules": [],
    })
    assert out["segmentId"]
    assert db.one("SELECT match_mode FROM segments WHERE id = ?",
                  (out["segmentId"],))["match_mode"] == "everyone"
    db.execute("DELETE FROM segments WHERE id = ?", (out["segmentId"],))


def test_a_group_the_agent_invents_a_rule_for_is_refused(client):
    from app import tools

    with pytest.raises(tools.ToolError):
        tools.run("create_group", {"name": "Bad", "rules": [{"field": "DROP", "op": "eq", "value": "1"}]})


# ============================================== the link every email carries


def test_the_unsubscribe_link_is_absolute_and_signed(monkeypatch, client):
    """It shipped as `/u/{campaign}/{contact}` — a relative path with no host,
    served by nothing.

    In a mail client a path with no host does not resolve, so the link was dead
    in every message that went out. That is not cosmetic: an opt-out is legally
    required, Gmail's bulk rules demand one-click, and a reader who cannot
    leave presses SPAM instead — which is the most damaging signal a mailbox
    provider takes, against the customer's own Gmail account.
    """
    from app import mailer
    monkeypatch.setattr(mailer, "public_base", lambda: "https://panel.example.com")
    out = mailer._personalise("Leave: {{unsubscribe}}",
                              {"id": "p-1", "email": "a@b.c", "name": "A"}, "c-1")
    url = out.replace("Leave: ", "")
    assert url.startswith("https://panel.example.com/u/c-1/p-1/")
    # a token, so the link cannot be guessed for somebody else
    assert len(url.rsplit("/", 1)[1]) >= 16


def test_the_link_actually_unsubscribes(client, monkeypatch):
    from app import db, mailer
    from app.domain import iso
    from app.security import new_id

    monkeypatch.setattr(mailer, "public_base", lambda: "https://panel.example.com")
    cid = new_id("p")
    db.insert("contacts", {"id": cid, "name_en": "Go", "name_fa": "Go",
                           "email": "unsubme@example.com", "status": "subscribed",
                           "tags": db.dumps([]), "created_at": iso()})
    url = mailer._personalise("{{unsubscribe}}",
                              {"id": cid, "email": "unsubme@example.com", "name": "Go"}, "c-1")
    path = url.replace("https://panel.example.com", "")

    assert client.get(path).status_code == 200
    assert db.one("SELECT status FROM contacts WHERE id = ?", (cid,))["status"] == "unsubscribed"
    # BOTH, or deleting the contact later would quietly re-permit mailing them
    assert db.one("SELECT 1 FROM suppression WHERE email = ?", ("unsubme@example.com",))


def test_a_guessed_link_cannot_unsubscribe_somebody(client, monkeypatch):
    """Without a signature, a competitor could walk the whole list."""
    from app import db
    from app.domain import iso
    from app.security import new_id

    cid = new_id("p")
    db.insert("contacts", {"id": cid, "name_en": "Safe", "name_fa": "Safe",
                           "email": "safe@example.com", "status": "subscribed",
                           "tags": db.dumps([]), "created_at": iso()})

    r = client.get(f"/u/c-1/{cid}/not-a-real-signature")
    assert r.status_code == 200                       # a page, not a stack trace
    assert "did not work" in r.text.lower()
    assert db.one("SELECT status FROM contacts WHERE id = ?", (cid,))["status"] == "subscribed"


def test_one_click_answers_the_mail_client(client, monkeypatch):
    """Gmail POSTs to the URL itself. A 404 here is why the button does nothing."""
    from app import db, mailer
    from app.domain import iso
    from app.security import new_id

    monkeypatch.setattr(mailer, "public_base", lambda: "https://panel.example.com")
    cid = new_id("p")
    db.insert("contacts", {"id": cid, "name_en": "Click", "name_fa": "Click",
                           "email": "oneclick@example.com", "status": "subscribed",
                           "tags": db.dumps([]), "created_at": iso()})
    path = mailer._personalise("{{unsubscribe}}",
                               {"id": cid, "email": "oneclick@example.com", "name": "C"},
                               "c-1").replace("https://panel.example.com", "")

    assert client.post(path).status_code == 200
    assert db.one("SELECT status FROM contacts WHERE id = ?", (cid,))["status"] == "unsubscribed"


def test_the_headers_offer_one_click_only_when_it_can_work(monkeypatch):
    """`List-Unsubscribe-Post` without a URL makes the button do nothing."""
    from app import mailer
    monkeypatch.setattr(mailer, "public_base", lambda: "https://panel.example.com")
    with_url = mailer._unsub_headers({"reply_to": "hi@b.c"}, "c-1", "p-1")
    assert "https://panel.example.com/u/" in with_url["List-Unsubscribe"]
    assert with_url["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    monkeypatch.setattr(mailer, "public_base", lambda: "")
    without = mailer._unsub_headers({"reply_to": "hi@b.c"}, "c-1", "p-1")
    assert "mailto:" in without["List-Unsubscribe"]
    assert "List-Unsubscribe-Post" not in without


# ============================================ every setup route is an owner's


def test_the_whole_setup_surface_needs_settings_write():
    """`/setup/reopen` took only `current_user`, so any signed-in role — a
    viewer included — could flip `setupComplete` back to false and change what
    the whole panel shows to everybody. Its docstring said "an owner"; the
    code did not.

    Checked as a family rather than one route, because the next one added
    would be just as easy to get wrong.
    """
    import inspect

    from app.routers import setup as setup_router

    ungated = []
    for name, fn in vars(setup_router).items():
        if not callable(fn) or not hasattr(fn, "__module__"):
            continue
        if fn.__module__ != setup_router.__name__ or name.startswith("_"):
            continue
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        if "@router." not in src and "def " + name not in src:
            continue
        # `/config` is deliberately public — it brands the sign-in screen
        if name == "config":
            continue
        if "requires(" not in src:
            ungated.append(name)

    assert not ungated, f"setup routes with no permission gate: {ungated}"


def test_a_password_change_needs_the_current_one():
    """The endpoint the panel had no screen for."""
    import inspect

    from app.routers import auth as auth_router

    src = inspect.getsource(auth_router.change_password)
    assert "verify_password" in src, "it would change a password without checking the old one"
    # and every other session ends, which is the point of changing it
    assert "refresh_tokens" in src and "revoked = 1" in src


# ============================================ a wrapper that hid two features


def test_async_renders_a_query_object_and_plain_children():
    """`Async` took destructured props and a FUNCTION child. Handed a query
    object and JSX — which is what anyone writes who already has the query —
    it saw `data: undefined` and returned null.

    Two finished features shipped rendering nothing that way. A component
    whose misuse produces an empty page rather than an error will be misused
    again, so it accepts both shapes now.
    """
    import inspect

    from app import db as _  # noqa: F401  (keeps the import block honest)

    src = open("../src/ui/state.jsx", encoding="utf-8").read()
    assert "query ?? {" in src, "Async no longer accepts a query object"
    assert "typeof children === 'function'" in src, "Async no longer accepts plain children"
