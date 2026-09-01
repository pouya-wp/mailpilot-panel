"""Conversations with the agent, kept.

Until now the chat box forgot everything the moment the page reloaded. That was
a deliberate early choice — a chat log invites people to treat an agent as a
chatbot and scroll back through it instead of looking at what it DID. Campaigns
were meant to be the durable record.

It was the wrong call for one reason: the operator could not carry on. A
question answered on Tuesday could not be followed up on Wednesday, and the
"make it shorter" kind of refinement only worked inside one page view.

So conversations persist now, with two things kept deliberately narrow:

  * A conversation belongs to the USER who had it, not to the workspace. Two
    people sharing a panel do not share drafts they were still thinking about.
  * Only the text is stored. The draft an answer carried is not — it either
    became a campaign, which has its own record, or it was discarded. Keeping a
    frozen copy would mean showing an old draft next to a campaign that has
    since been edited.

Titles are the first thing the operator said, trimmed. Asking a model to name
a conversation costs a call and a wait to produce something the first sentence
already says.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..deps import Principal, current_user
from ..domain import iso, paginate
from ..schemas import Body
from ..security import new_id

router = APIRouter(prefix="/chats", tags=["chats"])

#: Longest conversation we will replay to the model or the screen. Past this,
#: the older turns stop being context and start being cost.
MAX_TURNS = 200
TITLE_CHARS = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  title      TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chats_user ON chats(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_turns (
  id         TEXT PRIMARY KEY,
  chat_id    TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role       TEXT NOT NULL,
  text       TEXT NOT NULL DEFAULT '',
  meta       TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_chat ON chat_turns(chat_id, created_at);
"""


class TurnIn(Body):
    role: str
    text: str = ""
    meta: dict | None = None


class ChatPatch(Body):
    title: str


def _owned(chat_id: str, user_id: str):
    """A conversation is only ever readable by the person who had it."""
    row = db.one("SELECT * FROM chats WHERE id = ?", (chat_id,))
    if row is None or row["user_id"] != user_id:
        # 404 rather than 403: telling someone a conversation exists but is not
        # theirs is itself a disclosure.
        raise HTTPException(status_code=404, detail="No such conversation")
    return row


def _ser(row, turns: int = 0) -> dict:
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "turns": turns,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


@router.get("")
def list_chats(
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    principal: Principal = Depends(current_user),
) -> dict:
    rows = db.query(
        "SELECT * FROM chats WHERE user_id = ? ORDER BY updated_at DESC", (principal.id,)
    )
    out = paginate(rows, page, size)
    counts = {
        r["chat_id"]: r["n"]
        for r in db.query(
            "SELECT chat_id, COUNT(*) n FROM chat_turns GROUP BY chat_id"
        )
    }
    out["items"] = [_ser(r, counts.get(r["id"], 0)) for r in out["items"]]
    return out


@router.post("", status_code=201)
def create_chat(principal: Principal = Depends(current_user)) -> dict:
    now = iso()
    cid = new_id("chat")
    db.insert("chats", {"id": cid, "user_id": principal.id, "title": "",
                        "created_at": now, "updated_at": now})
    return _ser(db.one("SELECT * FROM chats WHERE id = ?", (cid,)))


@router.get("/{chat_id}")
def read_chat(chat_id: str, principal: Principal = Depends(current_user)) -> dict:
    row = _owned(chat_id, principal.id)
    turns = db.query(
        "SELECT * FROM chat_turns WHERE chat_id = ? ORDER BY created_at LIMIT ?",
        (chat_id, MAX_TURNS),
    )
    return {
        **_ser(row, len(turns)),
        "turns": [
            {"id": t["id"], "role": t["role"], "text": t["text"],
             "meta": db.loads(t["meta"], {}), "at": t["created_at"]}
            for t in turns
        ],
    }


@router.post("/{chat_id}/turns", status_code=201)
def add_turn(chat_id: str, payload: TurnIn,
             principal: Principal = Depends(current_user)) -> dict:
    row = _owned(chat_id, principal.id)
    if payload.role not in {"user", "agent"}:
        raise HTTPException(status_code=422, detail="role must be 'user' or 'agent'")

    now = iso()
    tid = new_id("turn")
    with db.transaction():
        db.insert("chat_turns", {
            "id": tid, "chat_id": chat_id, "role": payload.role,
            "text": payload.text[:8000],
            "meta": db.dumps(payload.meta or {}),
            "created_at": now,
        })
        patch = {"updated_at": now}
        # The first thing the operator said becomes the title. Naming it with a
        # model call would cost a request and a wait to say what that sentence
        # already says.
        if not row["title"] and payload.role == "user" and payload.text.strip():
            words = payload.text.strip().replace("\n", " ")
            patch["title"] = words[:TITLE_CHARS] + ("…" if len(words) > TITLE_CHARS else "")
        db.update("chats", chat_id, patch)

    return {"id": tid, "at": now}


@router.patch("/{chat_id}")
def rename_chat(chat_id: str, payload: ChatPatch,
                principal: Principal = Depends(current_user)) -> dict:
    _owned(chat_id, principal.id)
    db.update("chats", chat_id, {"title": payload.title.strip()[:120], "updated_at": iso()})
    return _ser(db.one("SELECT * FROM chats WHERE id = ?", (chat_id,)))


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: str, principal: Principal = Depends(current_user)) -> None:
    _owned(chat_id, principal.id)
    with db.transaction():
        # explicit rather than relying on the cascade: SQLite enforces foreign
        # keys only when the pragma is on, and a stale turn is invisible rubbish
        db.execute("DELETE FROM chat_turns WHERE chat_id = ?", (chat_id,))
        db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
