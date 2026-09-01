"""What the agent actually thinks with.

Every model call in the product goes through here, for two reasons.

First, GROUNDING. A marketing agent that invents an audience size or quotes a
campaign that never ran is worse than no agent at all, so every prompt is sent
with `snapshot()` — the real counts, the real segment names, the real recent
results — and the system prompt forbids inventing the rest. The model decides
what to do; it is not asked to remember what is true.

Second, FALLBACK. A deployment with no key, or one whose card expired on a
Sunday, still has to render a working panel. Every function here raises
`AIUnavailable` rather than failing hard, and the routes above catch it and
answer with something honest.

The persona comes from `deployment.agent_persona()`, so the agent a customer
talks to is the one their implementer configured — same name, same tone, same
guardrails — rather than a generic assistant wearing a logo.
"""

from __future__ import annotations

from typing import Any

from . import db, deployment, tools
from .ai_provider import (
    AIUnavailable,
    complete_json,
    complete_json_searching,
    search,
)

# ------------------------------------------------------------------ grounding


def snapshot() -> dict[str, Any]:
    """The account as the agent is allowed to know it.

    Deliberately small. A prompt carrying every contact would cost more and
    reason worse than one carrying the shape of the list.
    """
    segments = db.query("SELECT id, name_en, size FROM segments ORDER BY size DESC LIMIT 12")
    recent = db.query(
        "SELECT name_en, status, recipients, sent, opens, clicks, revenue "
        "FROM campaigns ORDER BY created_at DESC LIMIT 6"
    )
    contacts = db.scalar("SELECT COUNT(*) FROM contacts", default=0)
    subscribed = db.scalar("SELECT COUNT(*) FROM contacts WHERE status = 'subscribed'", default=0)
    voice = db.one("SELECT * FROM brand_voice WHERE id = 1")
    # `axes` is a set of 0-100 sliders (formal, warm, brief, bold); the model
    # reads them better as named levels than as raw numbers.
    # Switched off means the numbers stop being sent, not merely stop being
    # drawn. A prompt carrying sliders the deployment has disowned is the
    # agent being steered by something nobody is looking at any more.
    axes = (db.loads(voice["axes"], [])
            if voice and deployment.get().get("voice_axes", 1) else [])

    return {
        "contacts": {"total": contacts, "reachable": subscribed},
        "segments": [
            {"id": r["id"], "name": r["name_en"], "size": r["size"]} for r in segments
        ],
        "recentCampaigns": [
            {
                "name": r["name_en"],
                "status": r["status"],
                "sent": r["sent"],
                "openRate": round(r["opens"] / r["sent"] * 100, 1) if r["sent"] else None,
                "clickRate": round(r["clicks"] / r["sent"] * 100, 1) if r["sent"] else None,
                "revenue": r["revenue"],
            }
            for r in recent
        ],
        "brandVoice": {
            "axes": {a.get("id"): a.get("value") for a in axes if isinstance(a, dict)},
            "banned": db.loads(voice["banned"], []) if voice else [],
            "notes": (voice["notes"] if voice else "") or "",
        },
    }


def _ground(extra: str = "") -> str:
    """The system prompt: who the agent is, plus what is true."""
    import json

    parts = [deployment.agent_persona(), "", "Current account state (this is the ONLY data you may treat as fact):",
             json.dumps(snapshot(), ensure_ascii=False)]
    if extra:
        parts += ["", extra]
    return "\n".join(parts)


def _require_key() -> None:
    """Fail before building a prompt we cannot send."""
    if not deployment.ai_settings().ready:
        raise AIUnavailable("No API key set")


def _lang_rule(lang: str) -> str:
    return ("Write every human-readable string in Persian (Farsi)."
            if lang == "fa" else "Write every human-readable string in English.")


# --------------------------------------------------------------------- draft

DRAFT_SHAPE = """{
  "subject": "one subject line",
  "body": ["paragraph 1", "paragraph 2", "paragraph 3"],
  "cta": "button text, 2-4 words",
  "suggestions": [{"text": "alternative subject", "score": 82}],
  "reasoning": "one sentence on the angle you chose"
}"""


def draft_email(
    *,
    brief: str,
    goal: str,
    tone: str,
    length: str,
    lang: str,
    emoji: bool,
    personalize: bool,
    segment_name: str | None,
    creativity: int,
) -> dict[str, Any]:
    _require_key()
    paras = {"short": 2, "medium": 3, "long": 5}.get(length, 3)
    rules = [
        _lang_rule(lang),
        f"Write exactly {paras} short paragraphs.",
        f"The campaign goal is {goal}. Match a {tone} tone.",
        "Emoji are allowed, at most one." if emoji else "Use no emoji at all.",
        "Open with the {{first_name}} merge tag." if personalize else "Do not use merge tags.",
        "Give 4 alternative subject lines, each scored 0-100 for expected open rate.",
    ]
    if segment_name:
        rules.append(f"The audience is the segment '{segment_name}'. Write to those people specifically.")

    return complete_json(
        deployment.ai_settings(),
        system=_ground("\n".join(rules)),
        user=brief.strip() or "Write the next campaign you would send this audience, and explain the angle.",
        shape=DRAFT_SHAPE,
        # creativity is the reader's dial; 0-100 maps onto the useful half of
        # the temperature range, because above ~1.0 the copy stops being usable
        temperature=round(0.2 + (max(0, min(100, creativity)) / 100) * 0.8, 2),
    )


# ------------------------------------------------------------------- segment

SEGMENT_SHAPE = """{
  "name": "short segment name",
  "rules": [{"field": "ltv", "op": "gte", "value": "500"}],
  "explanation": "one sentence describing who this includes"
}"""

# Mirrors `_FIELDS` in routers/audience.py. If that grows, this string grows
# with it — a field the model does not know about is a rule it will never write.
SEGMENT_FIELDS = (
    "orders (number of purchases), ltv (lifetime spend, a plain number), "
    "score (engagement 0-100), country (two-letter code), status "
    "(subscribed|unsubscribed|bounced), device, tag, lastOpen (days since last open)"
)


def compile_segment(prompt: str, lang: str = "en") -> dict[str, Any]:
    _require_key()
    rules = [
        _lang_rule(lang),
        f"Allowed fields, and no others: {SEGMENT_FIELDS}.",
        "Allowed ops, and no others: eq, neq, gt, lt, gte, lte for numbers and text; "
        "`has` for tag; `before` or `after` for lastOpen.",
        "lastOpen values are a day count like \"90\". Money is a plain number, no symbol.",
    ]
    return complete_json(
        deployment.ai_settings(),
        system=_ground("\n".join(rules)),
        user=prompt,
        shape=SEGMENT_SHAPE,
        temperature=0.1,
    )


def complete_json_grounded(*, system_extra: str, user: str, shape: str,
                           max_tokens: int = 1600, temperature: float = 0.5,
                           images: list[str] | None = None,
                           token_floor: int = 0) -> dict[str, Any]:
    """A grounded completion for callers with their own prompt.

    Same persona and same account facts as everything else — a template the
    agent designs should sound like the agent that will send it — but the
    calling module supplies its own rules and its own shape.
    """
    _require_key()
    return complete_json(
        deployment.ai_settings(),
        system=_ground(system_extra),
        user=user,
        shape=shape,
        temperature=temperature,
        max_tokens=max_tokens,
        images=images,
        token_floor=token_floor,
    )


def research_leads(*, region: str, category: str, lang: str = "en") -> dict[str, Any]:
    """Go and look for organisations matching a region and a category.

    Always the searching endpoint, never the plain one. This is a question
    about the world — which businesses exist, where, and what they publish —
    and a model answering it from memory returns a confident list of places
    that may have closed years ago or never existed at all. If search is
    unavailable the caller is told, rather than being handed fiction.
    """
    from . import prospect

    _require_key()
    settings = deployment.ai_settings()
    return complete_json_searching(
        settings,
        system=_ground("\n".join(prospect.rules(region, category, lang))),
        user=f"Region: {region}\nLooking for: {category}",
        shape=prospect.SHAPE,
        # a page of leads with citations is a long document
        max_tokens=6000,
        token_floor=6000,
    )


# ---------------------------------------------------------------- the ask

#: The ask carries the account snapshot, the persona, the tool catalogue and a
#: JSON shape before the model writes a word. 1800 was set when it carried none
#: of that; below this the reply is cut off mid-object.
ASK_TOKENS = 4000

ASK_SHAPE = """{
  "reply": "your answer to the operator, 1-3 sentences",
  "intent": "campaign | audience | question | report | other",
  "confidence": 0.0,
  "draft": {"subject": "", "body": ["..."], "cta": ""},
  "audience": {"segmentId": "copy an id verbatim from segments above, or null", "reason": "why this audience"},
  "actions": [{"tool": "name from the list", "args": {}}],
  "steps": ["what you will do, one short line each"],
  "needs": ["anything you must be told before acting"]
}"""


def converse(message: str, *, lang: str = "en", history: list[dict] | None = None) -> dict[str, Any]:
    """The single entry point behind the panel's one input box.

    This is where the product's weight moved. Instead of the operator choosing a
    goal, a tone, a length, a segment and a send time across five screens, they
    say what they want and the agent fills all of that in — returning a draft
    and a target audience together, plus `needs` for anything it genuinely
    cannot infer. Only `needs` is ever put back to the reader as a question.
    """
    _require_key()
    rules = [
        _lang_rule(lang),
        "You are being asked to DO something, not to chat. Decide what the operator wants.",
        "If they want an email sent, put a complete draft in `draft`, and set "
        "`audience.segmentId` to an id copied EXACTLY from the segments list in the account "
        "state above. Never invent an id. If no segment fits, use null.",
        "If they asked a question about their own results, answer it from the account state and "
        "leave `draft` null.",
        "Put a question in `needs` ONLY if you genuinely cannot proceed without it. Prefer a "
        "sensible default and say what you assumed in `reply`.",
        "`steps` is what you are about to do, in the operator's words, not in system terms.",
        "",
        tools.describe(),
        "",
        "Anything that reaches a real inbox is shown to the operator for approval before "
        "it happens, so propose it plainly rather than asking permission in `reply` — "
        "they will see a button. Say in `reply` what you are proposing and why.",
    ]
    convo = ""
    if history:
        lines = [f"{h.get('role', 'user')}: {h.get('text', '')}" for h in history[-6:]]
        convo = "Earlier in this conversation:\n" + "\n".join(lines) + "\n\n"

    settings = deployment.ai_settings()

    # With search on, the question goes to the endpoint that carries the tool.
    # The model still decides whether to use it; most requests are about the
    # account's own data and never leave the building.
    if settings.search_enabled:
        rules.append(
            "You can search the web. Use it when the operator asks about something "
            "outside their own account — a competitor, a date, a price, what is "
            "happening in their market. Never claim you cannot look something up."
        )
        try:
            return complete_json_searching(
                settings,
                system=_ground("\n".join(rules)),
                user=f"{convo}{message}",
                shape=ASK_SHAPE,
                # The prompt carries the tool catalogue now, and reasoning
                # tokens come out of the same ceiling. At 1800 this call ran out
                # of room and fell through to the toolless path, which is how
                # the agent ended up insisting it could not search.
                max_tokens=ASK_TOKENS,
                token_floor=ASK_TOKENS,
            )
        except AIUnavailable as exc:
            # The tool-carrying endpoint can refuse for reasons the plain one
            # will not — an older model, a tool that is off for the account, a
            # reply that did not fit. Answering from the account's own data
            # beats not answering, but the model must be told what it has lost
            # rather than left to guess from a rule that quietly vanished.
            rules[-1] = (
                "Web search is NOT available on this request — the tool failed. "
                "Answer from the account state above. If the operator asked about "
                "something outside their account, say plainly that you could not "
                "look it up right now, and do not pretend you never could."
            )
            searched_failed = str(exc)
            out = complete_json(
                settings,
                system=_ground("\n".join(rules)),
                user=f"{convo}{message}",
                shape=ASK_SHAPE,
                temperature=0.4,
                max_tokens=ASK_TOKENS,
                token_floor=ASK_TOKENS,
            )
            out["_searchFailed"] = searched_failed
            return out

    return complete_json(
        settings,
        system=_ground("\n".join(rules)),
        user=f"{convo}{message}",
        shape=ASK_SHAPE,
        temperature=0.4,
        max_tokens=ASK_TOKENS,
        token_floor=ASK_TOKENS,
    )


# -------------------------------------------------------------------- research


def research(query: str, *, lang: str = "en") -> dict[str, Any]:
    """Look something up on the live web, through OpenAI's own search tool."""
    prompt = (
        f"{query}\n\n"
        f"{_lang_rule(lang)} Answer in at most 6 sentences. "
        "Be specific and cite what you used."
    )
    return search(deployment.ai_settings(), prompt)


__all__ = [
    "AIUnavailable",
    "complete_json_grounded",
    "compile_segment",
    "converse",
    "draft_email",
    "research",
    "snapshot",
]
