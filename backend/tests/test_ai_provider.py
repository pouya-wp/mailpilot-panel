"""The OpenAI client, without an OpenAI account.

Nobody running this suite has a key, so these tests intercept the HTTP layer
and assert the two things that would otherwise only be discovered in
production: that we send exactly what OpenAI's API expects, and that every way
the call can fail comes back as a recoverable `AIUnavailable` rather than as an
exception that reaches the customer as a 500.

The request bodies asserted here are the contract. If OpenAI changes it, these
fail loudly instead of the panel quietly falling back to the local writer and
nobody noticing for a month.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from app import ai_provider
from app.ai_provider import AISettings, AIUnavailable


class _Response:
    """The bare minimum of what urlopen returns, as a context manager."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def capture(monkeypatch):
    """Swap the network out and keep whatever the client tried to send."""
    sent: dict = {}

    def fake(req, timeout=None):
        sent["url"] = req.full_url
        sent["headers"] = {k.lower(): v for k, v in req.headers.items()}
        sent["body"] = json.loads(req.data.decode("utf-8"))
        sent["timeout"] = timeout
        return _Response(sent.get("reply", {}))

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)
    return sent


SETTINGS = AISettings(key="sk-test-key", model="gpt-4o-mini", search_enabled=True)


# ============================================================ request shape


def test_completion_posts_to_chat_completions_with_the_key(capture):
    capture["reply"] = {"choices": [{"message": {"content": '{"subject":"hi","body":["a"]}'}}],
                        "usage": {"total_tokens": 42}}

    ai_provider.complete_json(SETTINGS, system="be brief", user="write something",
                              shape='{"subject": "", "body": []}')

    assert capture["url"] == "https://api.openai.com/v1/chat/completions"
    assert capture["headers"]["authorization"] == "Bearer sk-test-key"
    assert capture["body"]["model"] == "gpt-4o-mini"
    # JSON mode is what makes the parse below safe to rely on
    assert capture["body"]["response_format"] == {"type": "json_object"}


def test_the_shape_is_shown_to_the_model_not_described(capture):
    """A literal example holds far better than a prose spec."""
    capture["reply"] = {"choices": [{"message": {"content": "{}"}}]}
    shape = '{"name": "short segment name", "rules": []}'

    ai_provider.complete_json(SETTINGS, system="compile", user="big spenders", shape=shape)

    system = capture["body"]["messages"][0]["content"]
    assert shape in system
    assert capture["body"]["messages"][1]["content"] == "big spenders"


def test_the_parsed_object_comes_back_with_its_token_cost(capture):
    capture["reply"] = {"choices": [{"message": {"content": '{"subject": "Spring is here"}'}}],
                        "usage": {"total_tokens": 118}}

    out = ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")

    assert out["subject"] == "Spring is here"
    assert out["_usage"] == 118


def test_search_uses_the_responses_api_and_the_web_search_tool(capture):
    """One vendor: search is OpenAI's own tool, not a second provider."""
    capture["reply"] = {"output": [{"type": "message", "content": [
        {"text": "Prices rose 4%.", "annotations": [
            {"url": "https://example.com/a", "title": "Report"},
            {"url": "https://example.com/a", "title": "Duplicate"},
        ]}]}]}

    out = ai_provider.search(SETTINGS, "what are competitors charging")

    assert capture["url"] == "https://api.openai.com/v1/responses"
    assert capture["body"]["tools"] == [{"type": "web_search"}]
    assert out["answer"] == "Prices rose 4%."
    # the same source cited twice is one source
    assert out["citations"] == [{"url": "https://example.com/a", "title": "Report"}]


def test_search_reads_text_from_message_blocks(capture):
    """`output_text` is absent whenever a tool ran, which for search is always."""
    capture["reply"] = {"output": [
        {"type": "web_search_call"},
        {"type": "message", "content": [{"text": "first"}, {"text": "second"}]},
    ]}
    assert ai_provider.search(SETTINGS, "q")["answer"] == "first\nsecond"


# ================================================================= failure


def test_no_key_is_refused_before_any_request(capture):
    empty = AISettings(key="", model="gpt-4o-mini")
    with pytest.raises(AIUnavailable):
        ai_provider.complete_json(empty, system="s", user="u", shape="{}")
    assert "url" not in capture  # nothing was sent


def test_search_off_for_this_deployment_is_refused(capture):
    off = AISettings(key="sk-x", model="gpt-4o-mini", search_enabled=False)
    with pytest.raises(AIUnavailable, match="switched off"):
        ai_provider.search(off, "anything")


def test_a_rejected_key_becomes_a_recoverable_error(monkeypatch):
    """401 must not reach the customer as a 500."""

    def fake(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                                     io.BytesIO(b'{"error":{"message":"Incorrect API key"}}'))

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)
    with pytest.raises(AIUnavailable) as caught:
        ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")
    # the provider's own words survive, so the operator knows what to fix
    assert "401" in str(caught.value)
    assert "Incorrect API key" in str(caught.value)


def test_an_unreachable_network_becomes_a_recoverable_error(monkeypatch):
    def fake(req, timeout=None):
        raise urllib.error.URLError("nodename nor servname provided")

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)
    with pytest.raises(AIUnavailable, match="Could not reach OpenAI"):
        ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")


def test_truncated_json_is_a_recoverable_error(capture):
    """max_tokens hit mid-object; the panel falls back rather than crashing."""
    capture["reply"] = {"choices": [{"message": {"content": '{"subject": "half'}}]}
    with pytest.raises(AIUnavailable, match="unparseable"):
        ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")


def test_verify_reports_the_model_that_answered(capture):
    capture["reply"] = {"model": "gpt-4o-mini-2024-07-18",
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {"total_tokens": 9}}
    out = ai_provider.verify("sk-test-key", "gpt-4o-mini")
    assert out["ok"] is True
    assert out["model"] == "gpt-4o-mini-2024-07-18"
    assert out["tokens"] == 9


# ============================================================== temperature


def test_creativity_maps_onto_a_usable_temperature_range(capture):
    """0-100 on the reader's dial, 0.2-1.0 at the provider. Above ~1 the copy
    stops being usable, so the top of the slider is not the top of the range."""
    from app import brain, deployment

    capture["reply"] = {"choices": [{"message": {"content": '{"subject":"s","body":["b"]}'}}]}
    original = deployment.ai_settings
    grounding = brain._ground
    deployment.ai_settings = lambda: SETTINGS
    # the prompt reads the account from the database; this test is about the
    # dial, so it is stubbed rather than dragging a schema in
    brain._ground = lambda extra="": "system"
    try:
        brain.draft_email(brief="x", goal="conversion", tone="friendly", length="short",
                          lang="en", emoji=False, personalize=False, segment_name=None,
                          creativity=0)
        assert capture["body"]["temperature"] == 0.2

        brain.draft_email(brief="x", goal="conversion", tone="friendly", length="short",
                          lang="en", emoji=False, personalize=False, segment_name=None,
                          creativity=100)
        assert capture["body"]["temperature"] == 1.0
    finally:
        deployment.ai_settings = original
        brain._ground = grounding


# ================================================ parameters models refuse


def test_the_modern_token_parameter_is_sent(capture):
    """`max_tokens` is refused outright by current models:

        "Unsupported parameter: 'max_tokens' is not supported with this
         model. Use 'max_completion_tokens' instead."
    """
    capture["reply"] = {"choices": [{"message": {"content": "{}"}}]}
    ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")

    assert "max_completion_tokens" in capture["body"]
    assert "max_tokens" not in capture["body"]


def test_verify_also_uses_the_modern_parameter(capture):
    capture["reply"] = {"model": "m", "choices": [{"message": {"content": "ok"}}]}
    ai_provider.verify("sk-test-key", "gpt-5.6-terra")
    assert "max_completion_tokens" in capture["body"]
    assert "max_tokens" not in capture["body"]


def test_a_refused_parameter_is_dropped_and_the_call_retried(monkeypatch):
    """The recovery that stops the NEXT retirement being an outage.

    Reasoning models already refuse `temperature` the same way `max_tokens`
    went. Rather than fail the operator's request over a parameter that was
    only an optimisation, the client drops the one the API named and retries.
    """
    seen: list[dict] = []

    def fake(req, timeout=None):
        body = json.loads(req.data.decode())
        seen.append(body)
        if "temperature" in body:
            raise urllib.error.HTTPError(
                req.full_url, 400, "Bad Request", {},
                io.BytesIO(json.dumps({"error": {
                    "code": "unsupported_parameter",
                    "param": "temperature",
                    "message": "Unsupported parameter: 'temperature' ...",
                }}).encode()),
            )
        return _Response({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)

    out = ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")

    assert out["ok"] is True
    assert len(seen) == 2                      # refused once, then succeeded
    assert "temperature" in seen[0]
    assert "temperature" not in seen[1]        # and only that field was dropped
    assert seen[1]["messages"] == seen[0]["messages"]


def test_the_retry_gives_up_rather_than_looping(monkeypatch):
    """A server that refuses everything must not spin."""
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        body = json.loads(req.data.decode())
        victim = next((k for k in ("temperature", "max_completion_tokens") if k in body), "model")
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            io.BytesIO(json.dumps({"error": {
                "code": "unsupported_parameter", "param": victim, "message": "no",
            }}).encode()),
        )

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)
    with pytest.raises(AIUnavailable):
        ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")
    assert calls["n"] <= 3


def test_an_ordinary_400_is_not_retried(monkeypatch):
    """Only `unsupported_parameter` earns a second attempt."""
    calls = {"n": 0}

    def fake(req, timeout=None):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            io.BytesIO(b'{"error":{"code":"invalid_api_key","message":"bad key"}}'),
        )

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)
    with pytest.raises(AIUnavailable, match="bad key"):
        ai_provider.complete_json(SETTINGS, system="s", user="u", shape="{}")
    assert calls["n"] == 1


# ============================================ reasoning, per endpoint


def test_chat_gets_the_flat_reasoning_effort(capture):
    """Chat Completions takes a string. Sending the Responses object here is
    what produced: "Unknown parameter: 'reasoning'." """
    capture["reply"] = {"choices": [{"message": {"content": "{}"}}]}
    thinking = AISettings(key="sk-test-key", model="gpt-5.6-terra", reasoning="high")

    ai_provider.complete_json(thinking, system="s", user="u", shape="{}")

    assert capture["body"]["reasoning_effort"] == "high"
    assert "reasoning" not in capture["body"]


def test_responses_gets_the_nested_reasoning_object(capture):
    capture["reply"] = {"output": [{"type": "message", "content": [{"text": "hi"}]}]}
    thinking = AISettings(key="sk-test-key", model="gpt-5.6-terra", reasoning="high")

    ai_provider.search(thinking, "anything")

    assert capture["body"]["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in capture["body"]


def test_reasoning_none_sends_nothing_at_all(capture):
    capture["reply"] = {"choices": [{"message": {"content": "{}"}}]}
    off = AISettings(key="sk-test-key", reasoning="none")

    ai_provider.complete_json(off, system="s", user="u", shape="{}")

    assert "reasoning" not in capture["body"]
    assert "reasoning_effort" not in capture["body"]


def test_an_unknown_parameter_is_also_dropped_and_retried(monkeypatch):
    """`unknown_parameter` is a different code from `unsupported_parameter`,
    and the first version of this recovery only caught the latter — so the
    reasoning error reached the operator as a raw 400."""
    seen: list[dict] = []

    def fake(req, timeout=None):
        body = json.loads(req.data.decode())
        seen.append(body)
        if "reasoning_effort" in body:
            raise urllib.error.HTTPError(
                req.full_url, 400, "Bad Request", {},
                io.BytesIO(json.dumps({"error": {
                    "code": "unknown_parameter",
                    "param": "reasoning_effort",
                    "message": "Unknown parameter: 'reasoning_effort'.",
                }}).encode()),
            )
        return _Response({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(ai_provider.urllib.request, "urlopen", fake)
    thinking = AISettings(key="sk-test-key", reasoning="low")

    out = ai_provider.complete_json(thinking, system="s", user="u", shape="{}")

    assert out["ok"] is True
    assert len(seen) == 2
    assert "reasoning_effort" not in seen[1]


# ==================================== the chat box can search the web


def test_a_searching_completion_carries_the_tool(capture):
    """The setting said "let the agent look things up online" while the chat
    box went to a toolless endpoint, so the agent truthfully answered that it
    could not search. This is the request that fixes that."""
    capture["reply"] = {"output": [{"type": "message", "content": [
        {"text": '{"reply": "done", "intent": "question"}',
         "annotations": [{"url": "https://example.com/a", "title": "A source"}]},
    ]}]}

    out = ai_provider.complete_json_searching(
        SETTINGS, system="be useful", user="what are competitors charging?", shape="{}")

    assert capture["url"] == "https://api.openai.com/v1/responses"
    assert capture["body"]["tools"] == [{"type": "web_search"}]
    assert out["reply"] == "done"
    assert out["_citations"] == [{"url": "https://example.com/a", "title": "A source"}]


def test_the_shape_and_system_prompt_reach_the_model(capture):
    capture["reply"] = {"output": [{"type": "message", "content": [{"text": "{}"}]}]}
    ai_provider.complete_json_searching(
        SETTINGS, system="YOU ARE NOVA", user="hello", shape='{"reply": ""}')

    instructions = capture["body"]["instructions"]
    assert "YOU ARE NOVA" in instructions
    assert '{"reply": ""}' in instructions
    assert capture["body"]["input"] == "hello"


def test_json_wrapped_in_a_code_fence_is_still_parsed(capture):
    """A model that has just used a tool often narrates or fences its output.
    Neither is worth failing a request over."""
    capture["reply"] = {"output": [{"type": "message", "content": [
        {"text": '```json\n{"reply": "fenced"}\n```'}]}]}

    out = ai_provider.complete_json_searching(SETTINGS, system="s", user="u", shape="{}")
    assert out["reply"] == "fenced"


def test_json_after_a_sentence_is_still_parsed(capture):
    capture["reply"] = {"output": [{"type": "message", "content": [
        {"text": 'Sure, here it is:\n{"reply": "prose"}\nlet me know!'}]}]}

    out = ai_provider.complete_json_searching(SETTINGS, system="s", user="u", shape="{}")
    assert out["reply"] == "prose"


def test_output_with_no_json_at_all_is_a_recoverable_error(capture):
    capture["reply"] = {"output": [{"type": "message", "content": [{"text": "I refuse."}]}]}
    with pytest.raises(AIUnavailable, match="usable JSON"):
        ai_provider.complete_json_searching(SETTINGS, system="s", user="u", shape="{}")


def test_loose_parsing_rejects_a_json_array():
    """The callers all unpack a dict; a list would fail later and further away."""
    assert ai_provider._loads_loose('[1, 2, 3]') is None
    assert ai_provider._loads_loose('') is None
    assert ai_provider._loads_loose('{"ok": true}') == {"ok": True}

# ======================================================= running out of room


def test_a_truncated_reply_says_so_instead_of_blaming_the_parser(monkeypatch):
    """The email designer's real failure, reported as "unparseable JSON".

    The deployment's per-request cap is sized for a chat reply. A whole HTML
    template does not fit, the model stopped mid-object, and the operator was
    shown a parser error with no action in it.
    """
    from app import ai_provider

    monkeypatch.setattr(ai_provider, "_post", lambda *a, **k: {
        "choices": [{"finish_reason": "length",
                     "message": {"content": '{"html": "<table><tr><td>cut off he'}}],
        "usage": {"total_tokens": 2000},
    })
    settings = ai_provider.AISettings(key="k", max_tokens=2000)
    with pytest.raises(ai_provider.AIUnavailable) as caught:
        # asks for more than the deployment allows, so the CAP is what bound it
        ai_provider.complete_json(settings, system="s", user="u", shape="{}",
                                  max_tokens=9000)

    said = str(caught.value)
    assert "cut off" in said and "2000" in said
    assert "Setup" in said           # names where the number lives
    assert "unparseable" not in said  # and not what it used to say


def test_it_does_not_blame_a_setting_that_was_not_the_constraint(monkeypatch):
    """Asking someone to raise a limit that was not binding wastes their time."""
    from app import ai_provider

    monkeypatch.setattr(ai_provider, "_post", lambda *a, **k: {
        "choices": [{"finish_reason": "length", "message": {"content": "{"}}],
        "usage": {},
    })
    generous = ai_provider.AISettings(key="k", max_tokens=8000)
    with pytest.raises(ai_provider.AIUnavailable) as caught:
        ai_provider.complete_json(generous, system="s", user="u", shape="{}",
                                  max_tokens=1600)

    said = str(caught.value)
    assert "1600" in said
    assert "Setup" not in said  # the deployment cap was not what stopped it


def test_the_per_request_cap_still_binds_ordinary_calls():
    from app.ai_provider import AISettings

    s = AISettings(key="k", max_tokens=2000)
    assert s.cap(9000) == 2000


def test_a_task_may_declare_a_need_the_chat_cap_would_strangle():
    """The designer, and nothing else today."""
    from app.ai_provider import HARD_MAX_TOKENS, AISettings

    s = AISettings(key="k", max_tokens=2000)
    assert s.cap(8000, floor=8000) == 8000
    # but the absolute ceiling is not negotiable
    assert s.cap(99000, floor=99000) == HARD_MAX_TOKENS


def test_a_floor_never_lowers_a_generous_deployment():
    from app.ai_provider import AISettings

    s = AISettings(key="k", max_tokens=6000)
    assert s.cap(8000, floor=4000) == 6000
