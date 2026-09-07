"""Beyondex Professional: a different email for every prospect.

The ordinary campaign path writes one piece of copy and merges a name into
it. This writes a separate email for each recipient, and the difference is
not cosmetic — it is the difference between "Hi {{first_name}}, we help
businesses like yours" going to a hundred people, and a hundred emails
that each say something true about the business receiving it.

FOUR STEPS, AND ALL FOUR MATTER.

  RESEARCH  — read the prospect's own website and say what it actually
              says. Every fact comes back labelled VERIFIED, INFERRED or
              UNKNOWN.
  STRATEGY  — decide which single offer fits this prospect, what problem
              to raise, and what proof (if any) may be cited. Can refuse:
              NEED_MORE_RESEARCH is a valid answer and is better than a
              confident generic email.
  WRITE     — the email, under the ten rules, in the brand's voice.
  REVIEW    — score it. Below the bar it is rewritten or held, never sent.

THE FACT STATUS RULE IS THE POINT. "I noticed you've just opened a second
branch" is a wonderful first line when it is true and a catastrophe when
it is guessed — the recipient knows instantly that the sender is
fabricating, and that is the impression the whole campaign leaves. So a
prospect fact may be stated as observed ONLY when the research marked it
VERIFIED. Inferred things may be raised as a question; unknown things may
not be raised at all.

WHY THE REVIEWER IS NOT OPTIONAL. A generator asked to be specific will,
on a thin website, become specific by inventing. The reviewer is a second
pass whose only job is to catch that, and its verdict gates the queue
rather than decorating it.
"""

from __future__ import annotations

from typing import Any

from . import brain, brandprofile, db, deployment
from .ai_provider import AIUnavailable, complete_json, complete_json_searching

# --------------------------------------------------------------- research

RESEARCH_SHAPE = """{
  "company": "",
  "website": "",
  "industry": "",
  "location": "",
  "services": [],
  "target_customers": [],
  "positioning": "",
  "verified_facts": ["a fact the site states, in one short sentence"],
  "inferred_points": ["a reasonable hypothesis, clearly not confirmed"],
  "recent_trigger": null,
  "likely_business_priorities": [],
  "research_sources": ["url actually read"],
  "research_confidence": 0
}"""

RESEARCH_RULES = [
    "Research ONE business and report only what you can support.",
    "",
    "Every entry in `verified_facts` must be something the business's own "
    "public pages state. If you cannot point at a source for it, it is not "
    "verified — put it in `inferred_points` or leave it out.",
    "`inferred_points` are reasonable hypotheses from the business context. "
    "They are NOT facts and will never be stated as observations.",
    "`recent_trigger` is only for something genuinely recent and dated — a new "
    "location, a launch, an announcement. Null is the normal answer.",
    "`research_sources` are URLs you actually read. An empty list means you "
    "found nothing, which is a valid and useful answer.",
    "`research_confidence` is 0-100. A business with one thin page scores low, "
    "and scoring it low is correct rather than unhelpful.",
    "",
    "Never invent a company size, a client list, revenue, staff numbers, or a "
    "problem the business is having. Those are the fabrications that make a "
    "cold email obviously machine-written.",
]


def research(contact: dict) -> dict[str, Any]:
    """Find out about one prospect. Needs web search; says so if it cannot.

    Uses whatever identifiers the contact carries — the website above all,
    which the email finder captured when it found them.
    """
    settings = deployment.ai_settings()
    if not settings.search_enabled:
        raise AIUnavailable(
            "Beyondex Professional needs web search to research each prospect. "
            "Turn it on in Setup — without it the research step would be "
            "inventing the businesses it claims to have read about."
        )

    known = [
        f"Email: {contact.get('email') or ''}",
        f"Name on file: {contact.get('name') or ''}",
        f"Company: {contact.get('company') or ''}",
        f"Website: {contact.get('website') or ''}",
        f"Country: {contact.get('country') or ''}",
    ]
    return complete_json_searching(
        settings,
        system=brain._ground("\n".join(RESEARCH_RULES)),
        user="Research this business:\n" + "\n".join(k for k in known if k.split(": ", 1)[1]),
        shape=RESEARCH_SHAPE,
        max_tokens=3000,
        token_floor=3000,
    )


# --------------------------------------------------------------- strategy

STRATEGY_SHAPE = """{
  "decision": "WRITE or NEED_MORE_RESEARCH",
  "why_not": "if NEED_MORE_RESEARCH, one sentence on what is missing",
  "chosen_offer": "the single offer name from the sender's list",
  "why_this_offer": "",
  "opening_fact": "the VERIFIED fact the first line will be built on, or empty",
  "problem_angle": "the problem to raise, phrased so an inferred one is a question",
  "outcome": "the outcome this offer creates for them",
  "proof_to_use": "a proof point from the sender's profile, or empty",
  "cta": "the low-friction ask"
}"""


def strategy(*, profile: dict, found: dict, goal: str = "") -> dict[str, Any]:
    """Decide what to say before writing a word of it.

    Separated from the writing on purpose. A model asked to decide and
    write at once will write first and justify afterwards, and the
    justification is where the invented facts get in.
    """
    rules = [
        "Match ONE prospect against ONE sender, and decide what the email should do.",
        "",
        "Choose exactly ONE offer. A first email that lists a catalogue is a "
        "brochure and gets deleted like one.",
        "`opening_fact` may ONLY be drawn from the research's `verified_facts`. "
        "If that list is empty, leave `opening_fact` empty — the email will "
        "simply open a different way. Never promote an inferred point to a fact.",
        "`proof_to_use` may ONLY be drawn from the sender's proof points. If the "
        "sender gave none, leave it empty and the email will claim none.",
        "",
        "Answer NEED_MORE_RESEARCH when there is not enough to say anything "
        "specific and true. That is a correct answer and a useful one: it holds "
        "the email back instead of sending a generic one under a personal "
        "pretence. Do not reach for it merely because the research is thin — "
        "an email can be relevant on industry and offer alone.",
    ]
    if goal.strip():
        rules.append(f"The campaign's goal, in the sender's words: {goal.strip()}")

    return complete_json(
        deployment.ai_settings(),
        system=brain._ground("\n".join(rules)),
        user=(
            "THE SENDER:\n" + brandprofile.as_prompt(profile)
            + "\n\nTHE PROSPECT (research):\n" + _readable(found)
        ),
        shape=STRATEGY_SHAPE,
        temperature=0.2,
    )


# ------------------------------------------------------------------ write

WRITE_SHAPE = """{
  "subject": "short, specific, not promotional",
  "body": ["paragraph 1", "paragraph 2", "paragraph 3"],
  "cta_line": "the closing ask, one sentence"
}"""

#: The ten rules, as the generator is told them. These are not
#: documentation: the reviewer scores against the same list, so a draft
#: that breaks one is caught rather than merely disapproved of in a file.
TEN_RULES = [
    "1. RIGHT PROSPECT FIRST. If this business is a poor fit for the offer, say "
    "less rather than forcing it. Never bend the offer to fit an address.",
    "2. THE SUBJECT MUST READ AS RELEVANT, NOT PROMOTIONAL. Short, specific, "
    "lower-case-natural. No hype, no exclamation marks, no ALL CAPS, no "
    "'exclusive offer', no emoji, no buzzwords, no colon-heavy sales formulas.",
    "3. THE FIRST LINE PROVES RELEVANCE. Open with the verified observation if "
    "there is one. Never open with 'My name is' or 'We are a leading'.",
    "4. PERSONALISE AROUND THEIR BUSINESS, NOT COMPLIMENTS. 'Great website' is "
    "not personalisation. Connect a real business context to a plausible "
    "priority — and if that priority is inferred, phrase it as a question, "
    "never as something you know.",
    "5. ONE EMAIL, ONE OFFER. The chosen offer only.",
    "6. SELL THE OUTCOME, NOT THE FEATURE LIST. Mention how it works only where "
    "that is needed to make the outcome believable.",
    "7. KEEP IT SHORT. Around 50-100 words in the body, three short paragraphs "
    "at most. No company history.",
    "8. LOW-FRICTION CTA. Ask whether it is relevant, or whether they want to "
    "see an example. Do not ask for a 30-minute call in a first email.",
    "9. NO EMPTY FOLLOW-UP LANGUAGE. Do not write 'just following up' or "
    "'circling back'; this is a first email and should not pretend otherwise.",
    "10. PROTECT DELIVERABILITY. No fabricated personalisation, no invented "
    "statistics, no urgency tricks, no attachments, no link stuffing. If you "
    "are unsure whether something is true, leave it out.",
]


def write(*, profile: dict, found: dict, plan: dict, lang: str = "en") -> dict[str, Any]:
    """Write the email itself, under the ten rules."""
    rules = [
        brain._lang_rule(lang),
        "Write ONE first-touch email to ONE business, following every rule below.",
        "",
        "== THE TEN RULES ==",
        *TEN_RULES,
        "",
        "== WHAT YOU MAY STATE AS FACT ==",
        "Only the strategy's `opening_fact`, and only if it is non-empty. "
        "Everything else about the prospect is either a question or unsaid. "
        "Inventing a detail about a business you are writing to cold is the "
        "single most damaging thing you can do here: they know instantly.",
        "",
        "Do not write a greeting line containing a merge tag placeholder — "
        "write the greeting normally, using the name you were given.",
        "Do not write a signature, a footer or an unsubscribe line. The "
        "template adds those.",
    ]
    return complete_json(
        deployment.ai_settings(),
        system=brain._ground("\n".join(rules)),
        user=(
            "THE SENDER:\n" + brandprofile.as_prompt(profile)
            + "\n\nTHE PROSPECT:\n" + _readable(found)
            + "\n\nTHE PLAN:\n" + _readable(plan)
        ),
        shape=WRITE_SHAPE,
        temperature=0.55,
    )


# ----------------------------------------------------------------- review

REVIEW_SHAPE = """{
  "scores": {
    "prospect_relevance": 0,
    "personalisation": 0,
    "subject": 0,
    "problem_clarity": 0,
    "single_offer": 0,
    "outcome_clarity": 0,
    "brand_voice": 0,
    "cta": 0,
    "hallucination_risk": 0,
    "spam_risk": 0
  },
  "score": 0,
  "verdict": "approve or rewrite or research",
  "problems": ["what is wrong, specifically"],
  "unsupported_claims": ["anything stated as fact that the research does not support"]
}"""

#: Where the reviewer's verdict takes the draft.
APPROVE_AT = 90      # ready to queue
REWRITE_AT = 80      # one rewrite, then re-review
RESEARCH_AT = 70     # research again before writing
# below RESEARCH_AT: held. Never queued.


def review(*, profile: dict, found: dict, draft: dict) -> dict[str, Any]:
    """Score a draft and say whether it may be sent.

    `hallucination_risk` and `spam_risk` are scored so that HIGH IS GOOD —
    100 means no risk found — because a single scale in one direction is
    the only way the average at the end means anything.
    """
    rules = [
        "You are reviewing a cold email before it is sent. You did not write it "
        "and you are not trying to like it.",
        "",
        "Score each criterion 0-100, where 100 is best. For "
        "`hallucination_risk` and `spam_risk`, 100 means NO risk found.",
        "",
        "The one that matters most: `unsupported_claims`. List anything the "
        "email states about the prospect as fact that the research does not "
        "carry in `verified_facts`. A single invented detail should pull "
        "`hallucination_risk` below 50 on its own.",
        "",
        "Check it against the ten rules the writer was given:",
        *TEN_RULES,
        "",
        "`verdict` is `approve` if it is ready, `rewrite` if the copy is the "
        "problem, `research` if the problem is that too little is known about "
        "this prospect to write anything specific.",
    ]
    return complete_json(
        deployment.ai_settings(),
        system=brain._ground("\n".join(rules)),
        user=(
            "THE SENDER:\n" + brandprofile.as_prompt(profile)
            + "\n\nTHE RESEARCH:\n" + _readable(found)
            + "\n\nTHE DRAFT:\n" + _readable(draft)
        ),
        shape=REVIEW_SHAPE,
        temperature=0.1,
    )


#: Below this on either risk criterion, nothing else about the draft can
#: rescue it. See `overall` — this is the difference between a quality
#: score and a safety check.
SAFETY_FLOOR = 70

#: The two criteria that are vetoes rather than contributions.
_RISKS = ("hallucination_risk", "spam_risk")


def overall(scored: dict) -> int:
    """One number from the ten, so the gate has something to compare.

    NOT A PLAIN AVERAGE, and the difference matters. An email that invents
    a fact about the recipient scores beautifully on the other nine
    criteria — the subject is sharp, the offer is single, the voice is
    right — and a mean lets it through at 91. That is precisely the email
    this whole pipeline exists to stop: the recipient knows instantly that
    the sender is fabricating, and that is the impression the campaign
    leaves behind.

    So the two risk criteria are vetoes. Score badly on either and the
    draft is worth no more than that score, whatever else it did well.
    Good copy cannot outweigh a made-up fact; it is what makes the made-up
    fact convincing.

    The model is asked for a summary `score` too, and ignored when it
    disagrees with its own criteria — a reviewer that scores eight things
    at 40 and then writes 95 in the summary is not a reviewer.
    """
    scores = scored.get("scores") or {}
    values = [v for v in scores.values() if isinstance(v, (int, float))]
    if not values:
        return int(scored.get("score") or 0)

    mean = round(sum(values) / len(values))
    risks = [scores[k] for k in _RISKS
             if isinstance(scores.get(k), (int, float))]
    if risks and min(risks) < SAFETY_FLOOR:
        return min(mean, int(min(risks)))
    return mean


# ------------------------------------------------------------------ the run


def compose_for(contact: dict, *, profile: dict, goal: str = "",
                lang: str = "en") -> dict[str, Any]:
    """The whole pipeline for one prospect.

    Returns what happened as well as what to send, because "held, because
    nothing about this business could be verified" is information the
    operator needs and a blank row is not.
    """
    found = research(contact)
    plan = strategy(profile=profile, found=found, goal=goal)

    if str(plan.get("decision") or "").upper().startswith("NEED"):
        return {
            "status": "research",
            "reason": plan.get("why_not") or "Not enough is known about this business yet.",
            "research": found, "plan": plan,
        }

    draft = write(profile=profile, found=found, plan=plan, lang=lang)
    scored = review(profile=profile, found=found, draft=draft)
    score = overall(scored)

    # One rewrite, then whatever it scores is what it gets. Rewriting in a
    # loop against the same reviewer converges on gaming it rather than on
    # a better email, and it bills the customer per attempt.
    if RESEARCH_AT <= score < APPROVE_AT:
        draft = write(profile=profile, found=found, plan=plan, lang=lang)
        scored = review(profile=profile, found=found, draft=draft)
        score = overall(scored)

    if score < RESEARCH_AT:
        return {
            "status": "held",
            "reason": "; ".join(scored.get("problems") or [])[:400]
                      or "The reviewer was not satisfied with this draft.",
            "score": score, "research": found, "plan": plan,
            "draft": draft, "review": scored,
        }

    return {
        "status": "ready",
        "score": score,
        "subject": str(draft.get("subject") or "").strip(),
        "body": _as_html(draft),
        "research": found, "plan": plan, "review": scored,
    }


def _as_html(draft: dict) -> str:
    """The paragraphs as the body HTML the template will wrap.

    Escaped: a business name with an ampersand in it should not be able to
    break the message, and the model is quoting names it read on a website.
    """
    from html import escape

    parts = [p for p in (draft.get("body") or []) if str(p).strip()]
    cta = str(draft.get("cta_line") or "").strip()
    if cta:
        parts.append(cta)
    return "".join(f'<p style="margin:0 0 1em">{escape(str(p).strip())}</p>' for p in parts)


def _readable(obj: Any) -> str:
    """A dict as something a model reads well: JSON, but only the filled-in
    parts. Empty keys invite it to fill them."""
    import json

    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items()
               if not k.startswith("_") and v not in (None, "", [], {})}
    return json.dumps(obj, ensure_ascii=False, indent=1)
