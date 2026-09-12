"""AI agents, the smart inbox, experiments and journeys.

The autonomy rule is enforced in one place, `_may_act_alone`, and every path
that would let an agent touch a customer goes through it. An agent set to
"suggest" cannot send, whatever the caller asks for — that setting is the only
thing standing between a misconfigured prompt and 25,000 real inboxes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..deps import Principal, module_enabled, requires
from ..domain import MAX_BODY, bi_in, iso, like, log, paginate, record_event, seeded_series
from ..schemas import (
    AgentIn,
    AgentPatch,
    AssignIn,
    ExperimentIn,
    JourneyIn,
    ReplyIn,
    StepIn,
)
from ..security import new_id
from ..serial import agent as ser_agent
from ..serial import experiment as ser_exp
from ..serial import journey as ser_journey
from ..serial import thread as ser_thread

def _needs(module: str):
    """Refuse a section this deployment was not sold."""
    return Depends(module_enabled(module))


router = APIRouter(tags=["agents"])

ALL_TOOLS = [
    "contacts.read", "contacts.write", "campaigns.write", "segments.write",
    "analytics.read", "brand.read", "inbox.read", "inbox.write",
    "domains.write", "suppression.write", "experiments.write", "crm.write",
]


def _agent(agent_id: str):
    row = db.one("SELECT * FROM agents WHERE id = ?", (agent_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return row


def _may_act_alone(row) -> bool:
    """Only a fully autonomous, active agent may reach a customer unattended."""
    return row["autonomy"] == "full" and row["status"] == "active"


# ================================================================ agents


@router.get("/agents")
def list_agents(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    return [ser_agent(r) for r in db.query("SELECT * FROM agents ORDER BY actions_today DESC")]


@router.get("/agents/tools", tags=["meta"])
def list_tools() -> list[str]:
    return ALL_TOOLS


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    out = ser_agent(_agent(agent_id))
    out["trace"] = _trace(agent_id)
    return out


def _trace(agent_id: str) -> list[dict]:
    """The run trace the Agent Studio shows. Derived from the agent's own tools
    so it can never advertise a capability the agent does not actually have."""
    row = _agent(agent_id)
    tools = db.loads(row["tools"])
    steps = [
        ("Loaded audience", "بارگذاری مخاطبان",
         "Pulled the target segment and its last 90 days of engagement.",
         "بخش هدف و تعامل ۹۰ روز اخیرش خوانده شد.",
         "contacts.read" if "contacts.read" in tools else None),
        ("Read brand voice", "خواندن لحن برند",
         "Applied the brand brain before drafting.",
         "پیش از نوشتن، لحن برند اعمال شد.",
         "brand.read" if "brand.read" in tools else None),
        ("Drafted output", "تولید خروجی",
         "Scored each candidate against this segment's history.",
         "هر گزینه بر اساس سابقهٔ همین بخش امتیاز گرفت.", None),
        ("Checked guardrails", "بررسی حفاظ‌ها",
         f"Daily budget {row['actions_today']}/{row['budget']} actions used.",
         f"سقف روزانه: {row['actions_today']} از {row['budget']} کار مصرف شد.", None),
        ("Requested approval" if row["autonomy"] != "full" else "Executed",
         "درخواست تأیید" if row["autonomy"] != "full" else "اجرا شد",
         "Autonomy is not 'full', so the action was queued for a human."
         if row["autonomy"] != "full" else "Autonomy is 'full', so the action ran unattended.",
         "استقلال «کامل» نیست، پس کار در صف تأیید انسان قرار گرفت."
         if row["autonomy"] != "full" else "استقلال «کامل» است، پس کار بدون نظارت اجرا شد.", None),
    ]
    return [
        {"title": {"en": en, "fa": fa}, "detail": {"en": den, "fa": dfa}, "tool": tool}
        for en, fa, den, dfa, tool in steps
    ]


@router.post("/agents", status_code=201)
def create_agent(payload: AgentIn, principal: Principal = Depends(requires("agents.deploy"))) -> dict:
    bad = [t for t in payload.tools if t not in ALL_TOOLS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown tools: {', '.join(bad)}")
    aid = new_id("ag")
    with db.transaction():
        db.insert("agents", {
            "id": aid, **bi_in(payload.name, "name"), **bi_in(payload.role, "role"),
            "emoji": payload.emoji, "tint": "linear-gradient(140deg,#5b8cff,#1b3fae)",
            "model": payload.model, "autonomy": payload.autonomy, "status": "paused",
            "runs": 0, "success": 0, "actions_today": 0, "budget": payload.budget,
            "temperature": payload.temperature, "last_run_at": None,
            "skills": db.dumps(payload.skills), "tools": db.dumps(payload.tools),
            "instructions": payload.instructions, "memory": db.dumps([]),
            "sparkline": db.dumps(seeded_series(14, base=5, trend=0.2, seed=7)),
            "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en="created an agent",
            action_fa="یک ایجنت ساخت", target=aid, tone="info")
    return ser_agent(_agent(aid))


@router.patch("/agents/{agent_id}")
def update_agent(
    agent_id: str, payload: AgentPatch, principal: Principal = Depends(requires("agents.deploy"))
) -> dict:
    _agent(agent_id)
    if payload.tools is not None:
        bad = [t for t in payload.tools if t not in ALL_TOOLS]
        if bad:
            raise HTTPException(status_code=422, detail=f"Unknown tools: {', '.join(bad)}")

    data: dict = {}
    if payload.name is not None:
        data |= bi_in(payload.name, "name")
    if payload.role is not None:
        data |= bi_in(payload.role, "role")
    for field, col in (("model", "model"), ("autonomy", "autonomy"), ("status", "status"),
                       ("instructions", "instructions"), ("budget", "budget"),
                       ("temperature", "temperature")):
        value = getattr(payload, field)
        if value is not None:
            data[col] = value
    if payload.tools is not None:
        data["tools"] = db.dumps(payload.tools)
    if payload.skills is not None:
        data["skills"] = db.dumps(payload.skills)

    if data:
        with db.transaction():
            db.update("agents", agent_id, data)
            if "autonomy" in data and data["autonomy"] == "full":
                log(kind="human", actor=principal.id,
                    action_en="granted an agent full autonomy",
                    action_fa="به یک ایجنت استقلال کامل داد", target=agent_id, tone="warn")
    return ser_agent(_agent(agent_id))


@router.post("/agents/{agent_id}/pause")
def pause_agent(agent_id: str, principal: Principal = Depends(requires("agents.deploy"))) -> dict:
    _agent(agent_id)
    with db.transaction():
        db.update("agents", agent_id, {"status": "paused"})
        log(kind="human", actor=principal.id, action_en="paused an agent",
            action_fa="یک ایجنت را متوقف کرد", target=agent_id, tone="warn")
    return ser_agent(_agent(agent_id))


@router.post("/agents/{agent_id}/resume")
def resume_agent(agent_id: str, principal: Principal = Depends(requires("agents.deploy"))) -> dict:
    _agent(agent_id)
    with db.transaction():
        db.update("agents", agent_id, {"status": "active"})
        log(kind="human", actor=principal.id, action_en="resumed an agent",
            action_fa="یک ایجنت را دوباره فعال کرد", target=agent_id, tone="good")
    return ser_agent(_agent(agent_id))


@router.post("/agents/{agent_id}/run")
def test_run(agent_id: str, principal: Principal = Depends(requires("agents.deploy"))) -> dict:
    """A dry run. Never touches a customer, whatever the autonomy setting."""
    row = _agent(agent_id)
    if row["actions_today"] >= row["budget"]:
        raise HTTPException(status_code=429, detail="Agent has used its daily action budget")
    with db.transaction():
        db.update("agents", agent_id, {
            "runs": row["runs"] + 1,
            "actions_today": row["actions_today"] + 1,
            "last_run_at": iso(),
        })
        log(kind="agent", actor=agent_id, action_en="completed a test run",
            action_fa="یک اجرای آزمایشی انجام داد", target=agent_id, tone="info")
    return {"ok": True, "dry_run": True, "may_act_alone": _may_act_alone(row),
            "trace": _trace(agent_id), "agent": ser_agent(_agent(agent_id))}


# ================================================================ inbox


@router.get("/inbox", dependencies=[_needs("inbox")])
def list_threads(
    filter: str = "all",
    intent: str = "all",
    q: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    _: Principal = Depends(requires("analytics.view")),
) -> dict:
    where = ["1=1"]
    params: list = []
    if filter == "needs":
        where.append("handled = 0")
    elif filter == "auto":
        where.append("handled = 1")
    if intent != "all":
        where.append("intent = ?")
        params.append(intent)
    if q:
        where.append("(from_en LIKE ? ESCAPE '\\' OR from_fa LIKE ? ESCAPE '\\' "
                     "OR email LIKE ? ESCAPE '\\' OR subject_en LIKE ? ESCAPE '\\')")
        params += [like(q)] * 4

    rows = db.query(
        f"SELECT * FROM threads WHERE {' AND '.join(where)} ORDER BY received_at DESC", params
    )
    out = paginate(rows, page, size)
    out["items"] = [ser_thread(r) for r in out["items"]]
    out["counts"] = {
        "needs": db.scalar("SELECT COUNT(*) FROM threads WHERE handled = 0", default=0),
        "auto": db.scalar("SELECT COUNT(*) FROM threads WHERE handled = 1", default=0),
        "all": db.scalar("SELECT COUNT(*) FROM threads", default=0),
    }
    return out


def _thread(thread_id: str):
    row = db.one("SELECT * FROM threads WHERE id = ?", (thread_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return row


@router.get("/inbox/{thread_id}")
def get_thread(thread_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    return ser_thread(_thread(thread_id))


def _send_reply(row, text: str) -> str:
    """Actually reply, over the customer's own Gmail. Returns the message id.

    Read the original back first: the thread row keeps Gmail's message id
    but not the conversation it belongs to, nor the RFC Message-ID that
    In-Reply-To has to quote. Without both, the reply arrives as a loose
    message with "Re:" on it rather than under the conversation.
    """
    from html import escape as html_escape

    from .. import deployment, google, mailer

    token = mailer.access_token()
    original = google.read_message(token, row["id"])

    d = deployment.get()
    subject = row["subject_en"] or ""
    if not subject.strip().lower().startswith("re:"):
        subject = f"Re: {subject}".strip()

    headers: dict[str, str] = {}
    if original.get("messageId"):
        headers["In-Reply-To"] = original["messageId"]
        # References carries the whole chain, so a long thread keeps
        # threading in clients that do not use Gmail's threadId.
        chain = (original.get("references") or "").strip()
        headers["References"] = f"{chain} {original['messageId']}".strip()

    # The draft is plain text written by the agent. Escaped, because a
    # customer's name or an operator's edit can contain < or &, and one
    # stray angle bracket otherwise eats the rest of the message.
    body_lines = [html_escape(line) for line in text.strip().splitlines() if line.strip()]
    html = "".join(f'<p style="margin:0 0 1em">{line}</p>' for line in body_lines) or (
        f"<p>{html_escape(text.strip())}</p>"
    )

    raw = google.build_message(
        to=row["email"],
        sender=d.get("from_email") or d.get("google_email") or "",
        sender_name=d.get("from_name") or d.get("brand_name") or "",
        subject=subject,
        html=html,
        text=text.strip(),
        reply_to=d.get("reply_to") or "",
        headers=headers,
    )
    # No unsubscribe header: this is a one-to-one answer to a message the
    # recipient sent us, not bulk mail, and offering to unsubscribe someone
    # from a conversation they started reads as a mistake.
    out = google.send_message(token, raw, thread_id=original.get("threadId") or "")
    return out.get("id") or ""


@router.post("/inbox/{thread_id}/copilot", dependencies=[_needs("inbox")])
def copilot(thread_id: str, principal: Principal = Depends(requires("content.edit"))) -> dict:
    """Draft a reply for a human to review. Never sends.

    Sending is `/reply`, which is a separate call a person has to make
    after reading this. Nothing here shortens that path, and an
    unsubscribe never reaches the generator at all.
    """
    from .. import replycopilot
    from ..ai_provider import AIUnavailable

    row = _thread(thread_id)
    try:
        out = replycopilot.draft_for(row, lang=_lang())
    except AIUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    replycopilot.save_draft(thread_id, out, row)
    log(kind="agent", actor=principal.id,
        action_en=f"drafted a reply ({out['status']})",
        action_fa="یک پیش‌نویس پاسخ نوشت", target=thread_id, tone="info")
    return {**out, "thread": ser_thread(_thread(thread_id))}


def _lang() -> str:
    from .. import deployment

    return deployment.get().get("default_lang") or "en"


@router.post("/inbox/{thread_id}/reply", dependencies=[_needs("inbox")])
def reply(
    thread_id: str, payload: ReplyIn, principal: Principal = Depends(requires("content.edit"))
) -> dict:
    from .. import google

    row = _thread(thread_id)

    # Three phases, in this order on purpose.
    #
    # 1. What must survive a failed send. The operator's edit, so a Gmail
    #    outage does not throw away what they just typed — and the opt-out,
    #    because someone who asked to be left alone has to be left alone
    #    whether or not we managed to send them a courtesy reply. Making
    #    that conditional on Gmail would mean a mailbox problem quietly
    #    keeps mailing people who asked us to stop.
    # Normalised once, here, so what is stored and what is sent are the same
    # string. `Lang` is `dict | str`, so this also has to accept both shapes --
    # reading `payload.text.en` off it raised AttributeError and surfaced as a
    # bare "Internal Server Error" every time an operator edited a draft.
    edited = bi_in(payload.text, "draft", limit=MAX_BODY) if payload.text is not None else None

    with db.transaction():
        if edited is not None:
            db.update("threads", thread_id, edited)
        if payload.send and row["intent"] == "unsubscribe":
            if db.one("SELECT 1 FROM suppression WHERE lower(email) = lower(?)", (row["email"],)) is None:
                db.insert("suppression", {"id": new_id("s"), "email": row["email"],
                                          "reason": "unsub", "created_at": iso()})
            db.execute("UPDATE contacts SET status='unsubscribed' WHERE lower(email)=lower(?)",
                       (row["email"],))

    if not payload.send:
        return ser_thread(_thread(thread_id))

    # 2. The send itself. The text as it will actually go out: the
    #    operator's edit if they made one, otherwise the draft on the row.
    body = ((edited["draft_en"] if edited is not None else row["draft_en"]) or "")
    if not body.strip():
        raise HTTPException(status_code=422, detail="There is nothing written to send yet")

    # The conversation may have moved since this draft was written. Sending
    # an answer to a message that has been superseded reads as not having
    # been listening, so it is refused and the operator regenerates. Only
    # when the operator has NOT just retyped it: an edit is them saying
    # they have read the thread as it stands.
    from .. import replycopilot

    if edited is None and replycopilot.is_stale(row):
        raise HTTPException(
            status_code=409,
            detail="This conversation has moved on since the draft was written. "
                   "Generate it again before sending.")
    try:
        _send_reply(row, body)
    except google.GoogleError as exc:
        # Say what went wrong. This route used to mark the thread handled
        # and write "approved and sent an agent reply" into the activity
        # log without contacting Gmail at all, so every reply looked sent
        # and none was.
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 3. Only now is it true. The thread is handled, the event counted and
    #    the log entry written, because now something was actually sent.
    with db.transaction():
        db.update("threads", thread_id, {"handled": 1})
        record_event("replied", email=row["email"])
        log(kind="human", actor=principal.id, action_en="approved and sent an agent reply",
            action_fa="پاسخ ایجنت را تأیید و ارسال کرد", target=thread_id, tone="good")
    return ser_thread(_thread(thread_id))


@router.post("/inbox/{thread_id}/assign", dependencies=[_needs("inbox")])
def assign(thread_id: str, payload: AssignIn, _: Principal = Depends(requires("content.edit"))) -> dict:
    _thread(thread_id)
    if payload.user_id and db.one("SELECT 1 FROM users WHERE id = ?", (payload.user_id,)) is None:
        raise HTTPException(status_code=404, detail="User not found")
    with db.transaction():
        db.update("threads", thread_id, {"assignee_id": payload.user_id})
    return ser_thread(_thread(thread_id))


@router.post("/inbox/{thread_id}/snooze", dependencies=[_needs("inbox")])
def snooze(thread_id: str, hours: int = Query(24, ge=1, le=720),
           _: Principal = Depends(requires("content.edit"))) -> dict:
    from ..domain import ago_iso
    _thread(thread_id)
    with db.transaction():
        db.update("threads", thread_id, {"snoozed_until": ago_iso(hours=-hours), "handled": 1})
    return ser_thread(_thread(thread_id))


# ================================================================ experiments


@router.get("/experiments")
def list_experiments(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    out = []
    for row in db.query("SELECT * FROM experiments ORDER BY created_at DESC"):
        variants = db.query("SELECT * FROM experiment_variants WHERE experiment_id = ? ORDER BY label", (row["id"],))
        out.append(ser_exp(row, variants))
    return out


@router.post("/experiments", status_code=201)
def create_experiment(payload: ExperimentIn, principal: Principal = Depends(requires("campaigns.write"))) -> dict:
    xid = new_id("x")
    with db.transaction():
        db.insert("experiments", {
            "id": xid, **bi_in(payload.name, "name"), "status": "running",
            "metric": payload.metric, "confidence": 0,
            "auto_promote": int(payload.auto_promote), "created_at": iso(),
        })
        for i, v in enumerate(payload.variants or [{"label": "A"}, {"label": "B"}]):
            db.insert("experiment_variants", {
                "id": f"{xid}-{i}", "experiment_id": xid,
                "label": str(v.get("label", chr(65 + i))),
                **bi_in(v.get("text"), "text"),
                "split": int(v.get("split", 100 // max(len(payload.variants or [1, 2]), 1))),
                "sent": 0, "rate": 0, "winner": 0,
            })
        log(kind="human", actor=principal.id, action_en="created an experiment",
            action_fa="یک آزمایش ساخت", target=xid, tone="info")
    row = db.one("SELECT * FROM experiments WHERE id = ?", (xid,))
    return ser_exp(row, db.query("SELECT * FROM experiment_variants WHERE experiment_id = ?", (xid,)))


@router.post("/experiments/{experiment_id}/promote")
def promote(experiment_id: str, principal: Principal = Depends(requires("campaigns.send"))) -> dict:
    row = db.one("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if row["confidence"] < 95:
        raise HTTPException(
            status_code=409,
            detail=f"Confidence is {row['confidence']}% — below the 95% threshold. "
                   "Promoting now would be calling noise.",
        )
    variants = db.query("SELECT * FROM experiment_variants WHERE experiment_id = ?", (experiment_id,))
    if not variants:
        raise HTTPException(status_code=409, detail="Experiment has no variants")
    best = max(variants, key=lambda v: v["rate"])
    with db.transaction():
        db.execute("UPDATE experiment_variants SET winner = 0 WHERE experiment_id = ?", (experiment_id,))
        db.update("experiment_variants", best["id"], {"winner": 1})
        db.update("experiments", experiment_id, {"status": "called"})
        log(kind="human", actor=principal.id, action_en=f"promoted variant {best['label']}",
            action_fa=f"نسخهٔ {best['label']} را ارتقا داد", target=experiment_id, tone="good")
    row = db.one("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    return ser_exp(row, db.query("SELECT * FROM experiment_variants WHERE experiment_id = ?", (experiment_id,)))


# ================================================================ journeys


@router.get("/journeys")
def list_journeys(_: Principal = Depends(requires("analytics.view"))) -> list[dict]:
    out = []
    for row in db.query("SELECT * FROM journeys ORDER BY enrolled DESC"):
        steps = db.query("SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY position", (row["id"],))
        out.append(ser_journey(row, steps))
    return out


def _journey(journey_id: str):
    row = db.one("SELECT * FROM journeys WHERE id = ?", (journey_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="Journey not found")
    return row


@router.get("/journeys/{journey_id}")
def get_journey(journey_id: str, _: Principal = Depends(requires("analytics.view"))) -> dict:
    row = _journey(journey_id)
    steps = db.query("SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY position", (journey_id,))
    return ser_journey(row, steps)


@router.post("/journeys", status_code=201)
def create_journey(payload: JourneyIn, principal: Principal = Depends(requires("campaigns.write"))) -> dict:
    jid = new_id("j")
    with db.transaction():
        db.insert("journeys", {
            "id": jid, **bi_in(payload.name, "name"), **bi_in(payload.trigger, "trigger"),
            "status": "paused", "enrolled": 0, "completed": 0, "conversion": 0,
            "agent_id": payload.agent, "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en="created a journey",
            action_fa="یک سفر مشتری ساخت", target=jid, tone="info")
    return ser_journey(_journey(jid), [])


@router.post("/journeys/{journey_id}/steps", status_code=201)
def add_step(journey_id: str, payload: StepIn, _: Principal = Depends(requires("campaigns.write"))) -> dict:
    _journey(journey_id)
    count = db.scalar("SELECT COUNT(*) FROM journey_steps WHERE journey_id = ?", (journey_id,), default=0)
    position = payload.position if payload.position is not None else count
    with db.transaction():
        # make room, so inserting in the middle does not collide on position
        db.execute(
            "UPDATE journey_steps SET position = position + 1 WHERE journey_id = ? AND position >= ?",
            (journey_id, position),
        )
        db.insert("journey_steps", {
            "id": new_id("st"), "journey_id": journey_id, "position": position,
            "type": payload.type, **bi_in(payload.label, "label"),
        })
    steps = db.query("SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY position", (journey_id,))
    return ser_journey(_journey(journey_id), steps)


@router.delete("/journeys/{journey_id}/steps/{step_id}", status_code=204)
def delete_step(journey_id: str, step_id: str, _: Principal = Depends(requires("campaigns.write"))) -> None:
    row = db.one("SELECT * FROM journey_steps WHERE id = ? AND journey_id = ?", (step_id, journey_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Step not found")
    with db.transaction():
        db.execute("DELETE FROM journey_steps WHERE id = ?", (step_id,))
        db.execute(
            "UPDATE journey_steps SET position = position - 1 WHERE journey_id = ? AND position > ?",
            (journey_id, row["position"]),
        )


@router.post("/journeys/{journey_id}/pause")
def pause_journey(journey_id: str, _: Principal = Depends(requires("campaigns.write"))) -> dict:
    _journey(journey_id)
    with db.transaction():
        db.update("journeys", journey_id, {"status": "paused"})
    steps = db.query("SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY position", (journey_id,))
    return ser_journey(_journey(journey_id), steps)


@router.post("/journeys/{journey_id}/resume")
def resume_journey(journey_id: str, _: Principal = Depends(requires("campaigns.write"))) -> dict:
    row = _journey(journey_id)
    steps = db.query("SELECT * FROM journey_steps WHERE journey_id = ? ORDER BY position", (journey_id,))
    if not steps:
        raise HTTPException(status_code=409, detail="A journey needs at least one step before it can run")
    with db.transaction():
        db.update("journeys", journey_id, {"status": "active"})
    return ser_journey(_journey(journey_id), steps)
