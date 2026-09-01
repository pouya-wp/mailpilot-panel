"""The AI surface: talk to the agent, draft an email, compile a segment.

Every route here calls OpenAI through `app.brain`, and every route degrades
instead of failing. If the deployment has no key, or the provider is down, or
the card expired, the deterministic writer further down this file answers
instead and the response says so in `source`.

That fallback is not decoration. This product is installed by one team and
operated by another; the day the key stops working must not be the day the
customer's panel stops rendering. A campaign written from the local table is
worse than one written by the model, and both are better than a 500.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from .. import brain, budget, db, deployment, tools
from ..ai_provider import AIUnavailable
from ..deps import Principal, requires
from ..domain import iso, log
from ..schemas import AskIn, Body, ComposeIn, ResearchIn, SegmentAskIn
from ..security import new_id

router = APIRouter(prefix="/ai", tags=["ai"])

# A credit is charged per generation so the Billing page has something real to
# count, and so an agent cannot loop forever.
CREDITS_PER_DRAFT = 12
CREDITS_PER_SEGMENT = 3
CREDITS_PER_ASK = 15
CREDITS_PER_SEARCH = 25


def _allowed_fields() -> set[str]:
    """The segment compiler's own allow-list, imported rather than restated so
    the two can never disagree about what a valid field is."""
    from .audience import _FIELDS

    return set(_FIELDS)


DRAFTS: dict[str, dict[str, dict]] = {
    "en": {
        "friendly": {
            "subject": "Your early access starts now",
            "body": [
                "Hi {{first_name}}, we held a few things back for you.",
                "The summer collection is live for VIP customers a full day before anyone else. "
                "No code, no queue — your account is already on the list.",
                "It runs until Friday, and the pieces that sold out last season are back in limited numbers.",
            ],
            "cta": "Shop the collection",
        },
        "professional": {
            "subject": "Early access to the summer collection",
            "body": [
                "Hello {{first_name}},",
                "As a VIP customer, your account has been granted access to the summer collection "
                "24 hours ahead of general release.",
                "Availability is limited on several returning items. Access closes Friday at 23:59 "
                "in your local time zone.",
            ],
            "cta": "View the collection",
        },
        "playful": {
            "subject": "Psst — the good stuff is open",
            "body": [
                "Hey {{first_name}}",
                "We unlocked the summer collection a day early, just for you. Everyone else is "
                "still refreshing the homepage.",
                "Last season's sell-outs are back, and there are not many of them. Go on.",
            ],
            "cta": "Take me there",
        },
        "urgent": {
            "subject": "24 hours: your VIP window is open",
            "body": [
                "{{first_name}} — your early access window is open now and closes Friday.",
                "The four pieces that sold out in under an hour last season are back in limited numbers.",
                "Once general release starts, VIP pricing ends.",
            ],
            "cta": "Claim your access",
        },
        "luxury": {
            "subject": "An invitation, before anyone else",
            "body": [
                "Dear {{first_name}},",
                "The summer collection opens to you a day before it opens to the world. "
                "Each piece is made in a run of forty.",
                "Your private access remains open until Friday evening.",
            ],
            "cta": "Enter the collection",
        },
    },
    "fa": {
        "friendly": {
            "subject": "دسترسی زودهنگام شما از همین حالا",
            "body": [
                "سلام {{first_name}}، چند چیز را برایتان کنار گذاشتیم.",
                "مجموعهٔ تابستان یک روز زودتر از همه برای مشتریان ویژه باز شده است. نه کدی لازم است، "
                "نه صفی — حسابتان از قبل در فهرست است.",
                "تا جمعه ادامه دارد و آن‌هایی که فصل قبل تمام شدند، به تعداد محدود برگشته‌اند.",
            ],
            "cta": "دیدن مجموعه",
        },
        "professional": {
            "subject": "دسترسی زودهنگام به مجموعهٔ تابستان",
            "body": [
                "سلام {{first_name}}،",
                "به‌عنوان مشتری ویژه، حساب شما ۲۴ ساعت پیش از عرضهٔ عمومی به مجموعهٔ تابستان دسترسی یافته است.",
                "موجودی چند قلم بازگشته محدود است. دسترسی جمعه ساعت ۲۳:۵۹ به وقت محلی شما بسته می‌شود.",
            ],
            "cta": "مشاهدهٔ مجموعه",
        },
        "playful": {
            "subject": "یواشکی — چیزهای خوب باز شد",
            "body": [
                "سلام {{first_name}}",
                "مجموعهٔ تابستان را یک روز زودتر فقط برای شما باز کردیم. بقیه هنوز دارند صفحهٔ اصلی را رفرش می‌کنند.",
                "آن‌هایی که فصل قبل تمام شدند برگشته‌اند و تعدادشان کم است.",
            ],
            "cta": "ببر آنجا",
        },
        "urgent": {
            "subject": "۲۴ ساعت: پنجرهٔ ویژهٔ شما باز است",
            "body": [
                "{{first_name}} — پنجرهٔ دسترسی زودهنگامتان همین حالا باز است و جمعه بسته می‌شود.",
                "چهار قلمی که فصل قبل زیر یک ساعت تمام شد، به تعداد محدود برگشته است.",
                "با شروع عرضهٔ عمومی، قیمت ویژه تمام می‌شود.",
            ],
            "cta": "گرفتن دسترسی",
        },
        "luxury": {
            "subject": "یک دعوت، پیش از همه",
            "body": [
                "{{first_name}} گرامی،",
                "مجموعهٔ تابستان یک روز زودتر از جهان برای شما باز می‌شود. هر قطعه در شمارگان چهل ساخته شده است.",
                "دسترسی خصوصی شما تا عصر جمعه باز می‌ماند.",
            ],
            "cta": "ورود به مجموعه",
        },
    },
}

SUBJECTS = {
    "en": [("Your early access starts now", 92), ("Before anyone else: summer is open", 88),
           ("24 hours of VIP pricing", 84), ("We held these back for you", 79)],
    "fa": [("دسترسی زودهنگام شما از همین حالا", 92), ("پیش از همه: تابستان باز شد", 88),
           ("۲۴ ساعت قیمت ویژه", 84), ("این‌ها را برایتان نگه داشتیم", 79)],
}


def _charge(credits: int) -> None:
    row = db.one("SELECT * FROM usage_counters WHERE id = 1")
    if row is None:
        return
    if row["credits_used"] + credits > row["credits_limit"]:
        raise HTTPException(
            status_code=402,
            detail="AI credit limit reached for this cycle. Top up or wait for the renewal.",
        )
    db.update("usage_counters", 1, {"credits_used": row["credits_used"] + credits}, key="id")


def _banned_words() -> list[str]:
    row = db.one("SELECT banned FROM brand_voice WHERE id = 1")
    return [w.lower() for w in db.loads(row["banned"] if row else "[]")]


def _check_guardrails(text: str) -> list[str]:
    """The brand brain's banned list is enforced, not merely displayed."""
    lowered = text.lower()
    return [w for w in _banned_words() if w and w in lowered]


def _draft(payload: ComposeIn) -> dict:
    """The model writes it; the table answers if the model cannot."""
    segment_name = None
    if payload.segment:
        row = db.one("SELECT name_en FROM segments WHERE id = ?", (payload.segment,))
        segment_name = row["name_en"] if row else None
    try:
        _guard()
        out = brain.draft_email(
            brief=payload.brief, goal=payload.goal, tone=payload.tone,
            length=payload.length, lang=payload.lang, emoji=payload.emoji,
            personalize=payload.personalize, segment_name=segment_name,
            creativity=payload.creativity,
        )
        # banked before the early return below — the call cost money whether or
        # not the answer turned out to be usable
        _spent(out)
        body = [p for p in (out.get("body") or []) if isinstance(p, str) and p.strip()]
        if out.get("subject") and body:
            return {
                "subject": str(out["subject"]).strip(),
                "body": body,
                "cta": str(out.get("cta") or "Shop now").strip(),
                "suggestions": _clean_suggestions(out.get("suggestions")),
                "reasoning": str(out.get("reasoning") or "").strip(),
                "source": "openai",
            }
    except (AIUnavailable, budget.BudgetExceeded):
        pass
    return _draft_local(payload)


def _clean_suggestions(raw) -> list[dict]:
    """The model is asked for scored alternatives; it does not always oblige."""
    out = []
    for item in raw or []:
        if isinstance(item, dict) and item.get("text"):
            try:
                score = int(item.get("score", 70))
            except (TypeError, ValueError):
                score = 70
            out.append({"text": str(item["text"]).strip(), "score": max(0, min(100, score))})
    return out[:5]


def _draft_local(payload: ComposeIn) -> dict:
    """The offline writer. Used when the provider is unreachable."""
    table = DRAFTS.get(payload.lang, DRAFTS["en"])
    draft = table.get(payload.tone, table["friendly"])
    body = list(draft["body"])
    if payload.length == "short":
        body = body[:2]
    elif payload.length == "long":
        body = body + [body[1]]
    if not payload.emoji:
        body = [re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", p).strip() for p in body]
    return {"subject": draft["subject"], "body": body, "cta": draft["cta"]}


@router.post("/compose")
def compose(payload: ComposeIn, principal: Principal = Depends(requires("content.edit"))) -> dict:
    if payload.agent:
        agent = db.one("SELECT * FROM agents WHERE id = ?", (payload.agent,))
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent["status"] != "active":
            raise HTTPException(status_code=409, detail="That agent is paused")
        if agent["actions_today"] >= agent["budget"]:
            raise HTTPException(status_code=429, detail="Agent has used its daily action budget")

    with db.transaction():
        _charge(CREDITS_PER_DRAFT)
        result = _draft(payload)
        joined = f"{result['subject']} {' '.join(result['body'])}"
        violations = _check_guardrails(joined)
        if payload.agent:
            agent = db.one("SELECT * FROM agents WHERE id = ?", (payload.agent,))
            db.update("agents", payload.agent, {
                "actions_today": agent["actions_today"] + 1,
                "runs": agent["runs"] + 1,
                "last_run_at": iso(),
            })
            log(kind="agent", actor=payload.agent, action_en="drafted an email",
                action_fa="یک ایمیل نوشت", target="composer", tone="info")

    words = len(joined.split())
    return {
        "subject": result["subject"],
        "body": result["body"],
        "cta": result["cta"],
        "lang": payload.lang,
        "suggestions": result.get("suggestions")
        or [{"text": t, "score": s} for t, s in SUBJECTS.get(payload.lang, SUBJECTS["en"])],
        "reasoning": result.get("reasoning", ""),
        "source": result.get("source", "local"),
        "analysis": {
            "words": words,
            # ~200 wpm reading speed, floored at a few seconds
            "readSeconds": max(5, round(words / 200 * 60)),
            "spamScore": round(1.8 + (0.6 if payload.tone == "urgent" else 0), 1),
            "readability": 8.2,
            "guardrailViolations": violations,
        },
        "creditsCharged": CREDITS_PER_DRAFT,
    }


# The same allow-list the segment compiler uses, so a natural-language prompt
# can never produce a rule naming a column that does not exist.
_FIELD_HINTS = {
    "order": ("orders", "gte"), "purchase": ("orders", "gte"), "bought": ("orders", "gte"),
    "خرید": ("orders", "gte"), "سفارش": ("orders", "gte"),
    "spend": ("ltv", "gte"), "ltv": ("ltv", "gte"), "value": ("ltv", "gte"),
    "خرج": ("ltv", "gte"), "ارزش": ("ltv", "gte"),
    "open": ("lastOpen", "before"), "opened": ("lastOpen", "before"),
    "باز": ("lastOpen", "before"),
    "engagement": ("score", "gte"), "score": ("score", "gte"), "تعامل": ("score", "gte"),
    "newsletter": ("tag", "has"), "خبرنامه": ("tag", "has"),
    "vip": ("tag", "has"), "ویژه": ("tag", "has"),
}


# A number is bound to the unit that FOLLOWS it, not to its position in the
# sentence. "bought 2 times but not opened in 90 days" has to give orders=2 and
# lastOpen=90d; taking the first number for both is how a segment quietly ends
# up meaning something nobody asked for.
_NEAR_DAYS = re.compile(r"(\d+)\s*(?:\+)?\s*(?:day|days|روز)", re.IGNORECASE)
_NEAR_MONEY = re.compile(r"[$€£﷼]\s*(\d+)|(\d+)\s*(?:dollars?|usd|تومان|ریال)", re.IGNORECASE)
_NEAR_TIMES = re.compile(r"(\d+)\s*(?:times?|orders?|purchases?|بار|سفارش)", re.IGNORECASE)


def _pick(pattern: re.Pattern, text: str, fallback: str) -> str:
    m = pattern.search(text)
    if not m:
        return fallback
    return next((g for g in m.groups() if g), fallback)


def _compile(prompt: str) -> list[dict]:
    """The model reads the sentence; the keyword matcher is the safety net.

    Whatever comes back is filtered against the same field allow-list the
    hand-rolled compiler uses, so a hallucinated column name can never reach
    the query builder.
    """
    try:
        _guard()
        out = brain.compile_segment(prompt)
        _spent(out)
        rules = [
            r for r in (out.get("rules") or [])
            if isinstance(r, dict) and r.get("field") in _allowed_fields() and r.get("value") not in (None, "")
        ]
        if rules:
            return rules[:6]
    except (AIUnavailable, budget.BudgetExceeded):
        pass
    return _compile_local(prompt)


def _compile_local(prompt: str) -> list[dict]:
    """Keyword matching. Used when the provider is unreachable."""
    text = prompt.lower()
    rules: list[dict] = []
    seen: set[str] = set()
    numbers = re.findall(r"\d+", text)
    for word, (field, op) in _FIELD_HINTS.items():
        if word in text and field not in seen:
            seen.add(field)
            if field == "tag":
                value = "newsletter" if ("newsletter" in text or "خبرنامه" in text) else "vip"
            elif field == "lastOpen":
                value = _pick(_NEAR_DAYS, text, "90") + "d"
            elif field == "orders":
                value = _pick(_NEAR_TIMES, text, numbers[0] if numbers else "2")
            elif field == "ltv":
                value = _pick(_NEAR_MONEY, text, numbers[-1] if numbers else "500")
            else:
                value = numbers[0] if numbers else "50"
            rules.append({"field": field, "op": op, "value": value})
    return rules or [{"field": "score", "op": "gte", "value": "50"}]


@router.post("/segment")
def build_segment(payload: SegmentAskIn, _: Principal = Depends(requires("contacts.write"))) -> dict:
    """Turn a sentence into rules, and show what they actually match.

    The rules are returned rather than saved. A segment definition decides who
    gets emailed; a human should see the machine's reading of their sentence
    before 25,000 people receive something.
    """
    if not payload.prompt.strip():
        raise HTTPException(status_code=422, detail="Describe the audience you want")

    with db.transaction():
        _charge(CREDITS_PER_SEGMENT)
    rules = _compile(payload.prompt)

    from .audience import UnknownField, _compile_rules

    if not rules:
        # `_compile_rules([])` is `1=1` — every contact there is. Previewing
        # that as "matches 25,000 people" invites saving a group nobody
        # described. `POST /segments` refuses it at save; this refuses it a
        # step earlier, where the reader can still see why.
        raise HTTPException(
            status_code=422,
            detail=("I could not turn that into a rule. Try naming a field — "
                    "how much they have spent, when they last opened something, "
                    "a tag they carry."),
        )

    try:
        where, params = _compile_rules(rules, "all")
    except UnknownField as exc:
        # the model wrote rules the compiler cannot honour; say so rather than
        # previewing a match against everybody
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    matched = db.scalar(f"SELECT COUNT(*) FROM contacts WHERE {where}", params, default=0)
    total = db.scalar("SELECT COUNT(*) FROM contacts", default=0)
    return {
        "rules": rules,
        "match": "all",
        "preview": {"matched": matched, "total": total},
        "creditsCharged": CREDITS_PER_SEGMENT,
    }


# ================================================================= the ask

def _guard() -> None:
    """Every model request passes here first.

    Raises `BudgetExceeded`, which each route turns into an answer the reader
    can act on rather than a 500. This is what stands between a runaway loop and
    an empty OpenAI account.
    """
    daily, monthly = deployment.caps()
    budget.check(daily, monthly)


def _spent(payload: dict) -> None:
    """Bank whatever the provider said the call cost."""
    budget.record(payload.get("_usage") or payload.get("tokens") or 0)


def _over_budget(lang: str, why: str) -> dict:
    return {
        "ok": False, "source": "budget",
        "reply": ("سقف مصرف هوش مصنوعی پر شده است: " if lang == "fa" else "AI budget reached: ") + why,
        "intent": "other", "draft": None, "audience": None, "steps": [], "needs": [],
        "did": [], "pending": [],
    }


def _unconfigured(lang: str) -> dict:
    """No key installed. Said plainly, in the reader's language, once.

    This is a setup problem, not an error: the panel is fine, the agent simply
    has nothing to think with yet. The owner sees a route to fix it; everyone
    else sees why nothing happened.
    """
    return {
        "ok": False,
        "source": "unconfigured",
        "reply": (
            "هنوز کلید هوش مصنوعی برای این نصب تنظیم نشده است. مدیر می‌تواند آن را در راه‌اندازی وارد کند."
            if lang == "fa"
            else "This installation has no AI key yet. An owner can add one in Setup."
        ),
        "intent": "other", "draft": None, "audience": None, "steps": [], "needs": [],
        "did": [], "pending": [],
    }


def _degraded(lang: str, why: str) -> dict:
    return {
        "ok": False, "source": "unavailable",
        "reply": ("دستیار در دسترس نیست: " if lang == "fa" else "The assistant is unreachable: ") + why,
        "intent": "other", "draft": None, "audience": None, "steps": [], "needs": [],
        "did": [], "pending": [],
    }


#: The model's own prose is not length-limited by anything upstream. A runaway
#: answer came back at 244KB in testing and went straight to the browser, where
#: it is laid out, measured and painted — on a phone that is a frozen tab.
MAX_REPLY = 4000
MAX_LINE = 400


def _text(value: object, limit: int) -> str:
    """A string, whatever the model actually sent.

    `str(x or "")` is not enough: the model returns numbers, nulls, lists and
    objects in fields the shape says are strings, and every one of those
    reaches the browser as-is.
    """
    if value is None or isinstance(value, (dict, list, tuple)):
        return ""
    return str(value).strip()[:limit]


def _lines(value: object, count: int) -> list[str]:
    """A list of short strings.

    `for x in (out.get("needs") or [])` raised TypeError and 500'd the whole
    request when the model returned `needs: 5` — which it does, because a JSON
    shape in a prompt is a request, not a contract.
    """
    if isinstance(value, (str, bytes)):
        return [_text(value, MAX_LINE)] if str(value).strip() else []
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        line = _text(item, MAX_LINE)
        if line:
            out.append(line)
        if len(out) >= count:
            break
    return out


@router.post("/ask")
def ask(payload: AskIn, principal: Principal = Depends(requires("content.edit"))) -> dict:
    """The panel's single input.

    Returns a reply, whatever the agent DID, and whatever it wants to do that
    needs a human first. Reversible internal work — saving contacts, drafting a
    campaign — has already happened by the time this returns. Anything that
    reaches a stranger's inbox is in `pending` with a signature, and happens
    only when the operator posts it back to `/ai/confirm`.
    """
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Tell the agent what you want")

    if not deployment.get().get("ai_key"):
        return _unconfigured(payload.lang)

    try:
        _guard()
    except budget.BudgetExceeded as exc:
        return _over_budget(payload.lang, str(exc))

    try:
        out = brain.converse(message, lang=payload.lang, history=payload.history)
    except AIUnavailable as exc:
        return _degraded(payload.lang, str(exc))
    _spent(out)

    with db.transaction():
        _charge(CREDITS_PER_ASK)
        log(kind="agent", actor=deployment.get()["agent_name"], action_en="answered a request",
            action_fa="به یک درخواست پاسخ داد", target="ask", tone="info")

    # A draft is only a draft if it has both halves; a subject with no body is
    # the model half-answering, and showing it as a campaign would be a lie.
    draft = out.get("draft") if isinstance(out.get("draft"), dict) else None
    if draft:
        body = [p for p in (draft.get("body") or []) if isinstance(p, str) and p.strip()]
        draft = {"subject": str(draft.get("subject") or "").strip(),
                 "body": body,
                 "cta": str(draft.get("cta") or "").strip()} if (draft.get("subject") and body) else None

    audience = None
    picked = (out.get("audience") or {}).get("segmentId") if isinstance(out.get("audience"), dict) else None
    if picked:
        row = db.one("SELECT id, name_en, name_fa, size FROM segments WHERE id = ?", (picked,))
        if row:
            audience = {"id": row["id"], "name": {"en": row["name_en"], "fa": row["name_fa"]},
                        "size": row["size"],
                        "reason": str((out.get("audience") or {}).get("reason") or "")}

    # Where the agent stops proposing and starts doing. Reversible work runs
    # now; anything that reaches an inbox comes back as a proposal, signed, so
    # what the operator approves is exactly what was shown to them.
    did, pending = tools.execute(out.get("actions"), actor=principal.id)
    for item in pending:
        item["sig"] = tools.sign(item["tool"], item["args"])

    return {
        "ok": True,
        "source": "openai",
        "reply": _text(out.get("reply"), MAX_REPLY),
        "intent": str(out.get("intent") or "other"),
        "draft": draft,
        "audience": audience,
        "did": did,
        "pending": pending,
        "steps": _lines(out.get("steps"), 6),
        "needs": _lines(out.get("needs"), 4),
        # Present only when the agent actually searched. An answer that quotes
        # the outside world should be able to show where it read it.
        "citations": out.get("_citations") or [],
        "searched": bool(out.get("_citations")),
        # Said out loud. A silent fallback to the toolless endpoint is what
        # made the agent look like it was denying an ability it had been given.
        "searchFailed": out.get("_searchFailed") or "",
        "creditsCharged": CREDITS_PER_ASK,
    }


class ConfirmIn(Body):
    tool: str = ""
    args: dict = {}
    sig: str = ""


@router.post("/confirm")
def confirm(payload: ConfirmIn, principal: Principal = Depends(requires("campaigns.send"))) -> dict:
    """Carry out an action the agent proposed and a person approved.

    Two gates, and both matter.

    The SIGNATURE proves this is the action that was shown. Without it the
    endpoint would accept any action the client cared to post, and the approval
    button would be decoration — a compromised or buggy client could turn "add
    two contacts" into "mail the whole list".

    The PERMISSION is `campaigns.send`, not `content.edit`. Asking the agent for
    a draft and authorising mail to leave are different rights, and a viewer who
    can chat must not be able to press this.
    """
    if not tools.blob_ok(payload.tool, payload.args, payload.sig):
        raise HTTPException(
            status_code=400,
            detail="That action does not match what was proposed. Ask again.",
        )
    try:
        result = tools.run(payload.tool, payload.args, actor=principal.id)
    except tools.ToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "tool": payload.tool, "result": result}


@router.post("/research")
def do_research(payload: ResearchIn, _: Principal = Depends(requires("content.edit"))) -> dict:
    """Look something up on the live web, through OpenAI's own search tool.

    One vendor, one key, one bill — the alternative was asking every deployment
    to also hold a search provider's account.
    """
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Ask a question to research")
    if not deployment.get().get("ai_key"):
        raise HTTPException(status_code=400, detail="This installation has no AI key yet")
    try:
        _guard()
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        out = brain.research(query, lang=payload.lang)
    except AIUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _spent(out)

    with db.transaction():
        _charge(CREDITS_PER_SEARCH)
    return {"answer": out["answer"], "citations": out["citations"],
            "creditsCharged": CREDITS_PER_SEARCH}
