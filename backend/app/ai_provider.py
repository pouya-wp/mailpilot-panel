"""The OpenAI client.

Written against the stdlib on purpose. Everything else in this backend is raw
sqlite3, `hashlib.scrypt` and a hand-rolled JWT; adding the `openai` package
here would make this one module the only thing standing between the deployment
and a dependency tree it did not ask for. Two endpoints and a JSON body is the
whole surface we need.

Two calls matter:

  * `complete_json` — the agent thinking. Every prompt in this product wants a
    STRUCTURE back (a draft with a subject and paragraphs, a segment rule, a
    plan with steps), never prose, so the response format is pinned to JSON and
    the caller states the shape it expects.

  * `search` — the agent looking things up. This uses OpenAI's own web_search
    tool through the Responses API rather than a separate search vendor, so a
    deployment needs exactly one API key and one bill.

Failure is a first-class return value. A deployment with no key, an expired
card, or a network that blocks api.openai.com must still render a working
panel, so callers get `AIUnavailable` and fall back to the local writer rather
than a 500.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

# Overridable so a deployment can sit behind a proxy, an Azure endpoint, or a
# stub during testing. Defaults to OpenAI itself.
BASE_URL = os.environ.get("MAILPILOT_OPENAI_BASE", "").strip().rstrip("/") or "https://api.openai.com/v1"
CHAT_URL = f"{BASE_URL}/chat/completions"
RESPONSES_URL = f"{BASE_URL}/responses"

# Offered in the setup wizard. Kept here so the list the owner picks from and
# the list this module can actually talk to are the same list.
#
# Prices are USD per million tokens and are carried so the wizard can show what
# a deployment will cost before it is handed over — the difference between Sol
# and Luna is twenty-fold, and that is a decision the implementer should make
# on purpose rather than by accepting a default.
MODELS = [
    {"value": "gpt-5.6-sol", "label": "GPT-5.6 Sol", "alias": "gpt-5.6",
     "note": "flagship · complex professional work",
     "note_fa": "پرچمدار · کارهای حرفه‌ای پیچیده",
     "inPrice": 4.0, "outPrice": 20.0, "maxOutput": 128_000, "context": 1_050_000,
     "search": True},
    {"value": "gpt-5.6-terra", "label": "GPT-5.6 Terra", "alias": "",
     "note": "balances intelligence and cost",
     "note_fa": "تعادل هوش و هزینه",
     "inPrice": 2.0, "outPrice": 12.0, "maxOutput": 128_000, "context": 1_050_000,
     "search": True},
    {"value": "gpt-5.6-luna", "label": "GPT-5.6 Luna", "alias": "",
     "note": "cheapest · cost-sensitive workloads",
     "note_fa": "ارزان‌ترین · برای مصرف حساس به هزینه",
     "inPrice": 0.20, "outPrice": 1.20, "maxOutput": 128_000, "context": 1_050_000,
     "search": True},
]
MODEL_VALUES = {m["value"] for m in MODELS}
DEFAULT_MODEL = "gpt-5.6-terra"

# How hard the model thinks before answering. More reasoning costs output
# tokens, so this is a spend dial as much as a quality one.
REASONING = ["none", "low", "medium", "high", "xhigh", "max"]
DEFAULT_REASONING = "low"

# A single request must never be able to spend an unbounded amount. This is the
# ceiling the wizard cannot raise past, whatever it is configured with.
HARD_MAX_TOKENS = 8000
DEFAULT_MAX_TOKENS = 2000


class AIUnavailable(RuntimeError):
    """No key, no network, or the provider refused. Always recoverable."""


@dataclass(frozen=True)
class AISettings:
    key: str
    model: str = DEFAULT_MODEL
    search_enabled: bool = True
    temperature: float = 0.6
    reasoning: str = DEFAULT_REASONING
    #: per-request output ceiling, already clamped to HARD_MAX_TOKENS
    max_tokens: int = DEFAULT_MAX_TOKENS

    @property
    def ready(self) -> bool:
        return bool(self.key)

    def cap(self, wanted: int, *, floor: int = 0) -> int:
        """No caller may ask for more than this deployment allows.

        `floor` is for the handful of tasks that provably cannot work under a
        chat-sized ceiling — generating a whole email template is the only one
        today. It lifts THIS call above the deployment's per-request setting
        and nothing else: `HARD_MAX_TOKENS` still binds, the call is still
        recorded against the daily and monthly ledgers, and a runaway loop is
        still stopped by those. Without it the operator's only route to a
        working designer was to raise the global cap, which would also raise
        the ceiling on every chat turn — exactly what the cap exists to hold.
        """
        allowed = max(self.max_tokens, min(floor, HARD_MAX_TOKENS))
        return max(64, min(wanted, allowed, HARD_MAX_TOKENS))


def _post(url: str, key: str, payload: dict[str, Any], timeout: int = 60,
          *, _retries: int = 2) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]

        # Models disagree about which parameters they accept, and the set keeps
        # shrinking: `max_tokens` went first, `temperature` is already gone on
        # the reasoning models. When the API names the offending field, drop it
        # and try once more rather than failing the operator's request over a
        # parameter that was only ever an optimisation.
        rejected = _unsupported_parameter(detail)
        if rejected and rejected in payload and _retries:
            trimmed = {k: v for k, v in payload.items() if k != rejected}
            return _post(url, key, trimmed, timeout, _retries=_retries - 1)

        # 401 is a wrong key, 429 is quota — both are the operator's problem and
        # both must reach them as a sentence, not as a stack trace in a log file
        raise AIUnavailable(f"OpenAI returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AIUnavailable(f"Could not reach OpenAI: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise AIUnavailable(f"Could not reach OpenAI: {exc}") from exc


def _unsupported_parameter(detail: str) -> str | None:
    """The field name in a "we will not take that parameter" error.

    OpenAI reports it in a `param` field, e.g.
        {"error": {"code": "unknown_parameter", "param": "reasoning", ...}}
    """
    try:
        error = json.loads(detail).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return None
    # `unknown_parameter` is the one that says the endpoint has never heard of
    # the field at all; the others say it knows it but will not take it here.
    if error.get("code") not in {"unsupported_parameter", "unsupported_value",
                                 "unknown_parameter"}:
        return None
    param = error.get("param")
    return param if isinstance(param, str) and param else None


def _reasoning(settings: AISettings, *, endpoint: str) -> dict[str, Any]:
    """Reasoning effort, spelled the way the given endpoint spells it.

    The two APIs disagree, and there is no default parameter here on purpose —
    sending the Responses shape to Chat Completions is exactly the bug this
    signature exists to prevent:

        chat      ->  {"reasoning_effort": "low"}
        responses ->  {"reasoning": {"effort": "low"}}

    Omitted entirely when it is off: sending `"none"` and sending nothing are
    the same request to a model that does not reason, so the quieter form wins.
    """
    if not settings.reasoning or settings.reasoning == "none":
        return {}
    if endpoint == "chat":
        return {"reasoning_effort": settings.reasoning}
    return {"reasoning": {"effort": settings.reasoning}}


def verify(key: str, model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """One cheap round trip, so the wizard can say 'this key works' before the
    owner hands the panel to a customer rather than after."""
    if not key:
        raise AIUnavailable("No API key set")
    data = _post(
        CHAT_URL,
        key,
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            # the modern name; `max_tokens` is refused outright by current models
            "max_completion_tokens": 16,
        },
        timeout=25,
    )
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage") or {}
    return {"ok": True, "model": data.get("model", model), "reply": text.strip()[:40],
            "tokens": usage.get("total_tokens", 0)}


def complete_json(
    settings: AISettings,
    *,
    system: str,
    user: str,
    shape: str,
    temperature: float | None = None,
    max_tokens: int = 1600,
    images: list[str] | None = None,
    token_floor: int = 0,
) -> dict[str, Any]:
    """Ask for one JSON object.

    `shape` is appended to the system prompt as the contract. The model is far
    more reliable at holding a shape it has been shown than at holding one
    described in prose, so callers pass a literal example rather than a spec.

    `images` are data: URLs the model should LOOK at. Used by the email
    designer, where "make it like this" is a picture and describing it in
    words loses most of what the person meant.
    """
    if not settings.ready:
        raise AIUnavailable("No API key set")

    # A plain string when there are no images, so the ordinary call stays
    # byte-for-byte what it was; the array form appears only when it earns its
    # place, since not every deployment's model accepts it.
    content: Any = user
    if images:
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in images[:6]
        ]

    data = _post(
        CHAT_URL,
        settings.key,
        {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": f"{system}\n\nReturn ONLY valid JSON of exactly this shape:\n{shape}"},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": settings.temperature if temperature is None else temperature,
            # CLAMPED, not trusted. A caller asking for a huge completion — or a
            # bug looping through this function — cannot spend more than the
            # deployment's per-request ceiling.
            "max_completion_tokens": settings.cap(max_tokens, floor=token_floor),
            **_reasoning(settings, endpoint="chat"),
        },
    )
    choices = data.get("choices") or []
    if not choices:
        raise AIUnavailable("OpenAI returned no choices")
    content = choices[0].get("message", {}).get("content") or ""

    # Checked BEFORE parsing. A reply cut off by the token ceiling is half a
    # JSON object, and reporting that as a parse error sends the reader looking
    # for a fault in the provider instead of at a number they can change.
    if choices[0].get("finish_reason") == "length":
        allowed = settings.cap(max_tokens, floor=token_floor)
        # Which number to point at matters. Telling someone to raise a setting
        # that was not the binding constraint sends them to change the wrong
        # thing and watch it fail again.
        if allowed < max_tokens:
            why = (f"cut off at this deployment's per-request limit of {allowed} tokens. "
                   "Raise it in Setup, or ask for something shorter.")
        else:
            why = (f"cut off after {allowed} tokens, which is all this task asks for. "
                   "Ask for something shorter.")
        raise AIUnavailable("The reply was " + why)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AIUnavailable(f"OpenAI returned unparseable JSON: {content[:200]}") from exc
    if not isinstance(parsed, dict):
        raise AIUnavailable("OpenAI returned JSON that was not an object")
    parsed["_usage"] = (data.get("usage") or {}).get("total_tokens", 0)
    return parsed


def search(settings: AISettings, query: str, *, max_tokens: int = 900) -> dict[str, Any]:
    """Look something up on the live web.

    Uses OpenAI's built-in web_search tool rather than a second vendor. The
    answer comes back as prose with URL annotations, which is the right shape
    for "what are competitors doing this month" — the agent reads it, the
    operator sees where it came from.
    """
    if not settings.ready:
        raise AIUnavailable("No API key set")
    if not settings.search_enabled:
        raise AIUnavailable("Web search is switched off for this deployment")

    data = _post(
        RESPONSES_URL,
        settings.key,
        {
            "model": settings.model,
            "tools": [{"type": "web_search"}],
            "input": query,
            "max_output_tokens": settings.cap(max_tokens),
            **_reasoning(settings, endpoint="responses"),
        },
        timeout=90,
    )
    return {"answer": _output_text(data), "citations": _citations(data),
            "tokens": (data.get("usage") or {}).get("total_tokens", 0)}


def _output_text(data: dict[str, Any]) -> str:
    """Flatten a Responses payload to its text.

    The convenience field is `output_text`, but it is absent whenever the model
    used a tool, which for a search call is always — so the message blocks are
    walked instead.
    """
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()


def _citations(data: dict[str, Any]) -> list[dict[str, str]]:
    """Sources, de-duplicated by URL and in the order the model used them."""
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in data.get("output") or []:
        for part in item.get("content") or []:
            for note in part.get("annotations") or []:
                url = note.get("url")
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append({"url": url, "title": note.get("title") or url})
    return out[:8]


def complete_json_searching(
    settings: AISettings,
    *,
    system: str,
    user: str,
    shape: str,
    max_tokens: int = 1800,
    token_floor: int = 0,
) -> dict[str, Any]:
    """Ask for one JSON object, from a model that may search the web first.

    This is `complete_json` with the internet attached. It goes to the
    Responses API because that is the endpoint carrying the `web_search` tool,
    and the model decides on its own whether a question needs looking up — most
    do not, and a tool that is offered but unused costs nothing.

    Structured output is asked for in the PROMPT rather than pinned with a
    response-format parameter. Response formats and tool use interact
    differently across API versions, and a hard 400 here would take the whole
    chat down; a model that wraps its JSON in a code fence is recoverable, and
    `_loads_loose` recovers it.
    """
    if not settings.ready:
        raise AIUnavailable("No API key set")

    data = _post(
        RESPONSES_URL,
        settings.key,
        {
            "model": settings.model,
            "tools": [{"type": "web_search"}],
            "instructions": (
                f"{system}\n\n"
                "You may search the web when the answer depends on current information "
                "you were not given. Do not search for things already in the account "
                "state above.\n\n"
                f"Reply with ONLY a JSON object of exactly this shape, and no other text:\n{shape}"
            ),
            "input": user,
            "max_output_tokens": settings.cap(max_tokens, floor=token_floor),
            **_reasoning(settings, endpoint="responses"),
        },
        timeout=120,
    )

    parsed = _loads_loose(_output_text(data))
    if parsed is None:
        # Same reasoning as the chat endpoint: a reply stopped by the ceiling is
        # not malformed JSON, it is an unfinished one, and saying which is the
        # difference between a number the operator can change and a shrug.
        if (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
            allowed = settings.cap(max_tokens, floor=token_floor)
            raise AIUnavailable(
                f"The reply was cut off at {allowed} tokens before it finished. "
                "Raise the per-request token limit in Setup, or ask for less."
            )
        raise AIUnavailable("The model did not return usable JSON")
    parsed["_usage"] = (data.get("usage") or {}).get("total_tokens", 0)
    parsed["_citations"] = _citations(data)
    return parsed


def _loads_loose(text: str) -> dict[str, Any] | None:
    """Parse JSON that may be wearing a code fence or a sentence.

    A model told to emit only JSON usually does. When it has just used a tool
    it sometimes narrates first, or fences the block — neither is worth failing
    a request over, so the outermost object is extracted and parsed.
    """
    if not text:
        return None
    body = text.strip()

    if body.startswith("```"):
        body = body.split("```")[1] if "```" in body[3:] else body[3:]
        body = body.removeprefix("json").strip()

    try:
        out = json.loads(body)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        pass

    # last resort: the widest {...} span in the text
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        out = json.loads(body[start : end + 1])
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None
