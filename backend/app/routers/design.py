"""The template designer: images in, a sendable email template out.

The flow this serves is one sentence long — the operator hands over a few
pictures and the facts they want said, and gets back an HTML email they can
look at, edit, and then make the house style.

Three things are worth knowing about how it is built.

IMAGES ARE STORED, NOT INLINED. A model cannot see a file the operator picked,
and base64 inside the HTML would blow past Gmail's 100KB clipping limit after
two photos. So an upload becomes a row with a URL, the model is told the URLs
and what each picture is, and it writes `<img src>` tags pointing at them. The
same URLs work in the preview and in a real send.

THE HTML IS SANITISED ON THE WAY IN, EVERY TIME. Both when the model writes it
and when a human edits it. The preview iframe is sandboxed too, but a sandbox
is the second line of defence, not the first.

TEMPLATES ARE LINTED, NOT VALIDATED. Email clients disagree about almost
everything; a template that uses flexbox still sends, it just breaks in Outlook.
The operator is told before the whole list gets it, and decides.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Response

from .. import brain, budget, db, deployment, emaildesign, emailhtml
from ..ai_provider import AIUnavailable
from ..deps import Principal, current_principal, module_enabled, requires
from ..domain import iso, log
from ..schemas import Body
from ..security import new_id


def _needs(module: str):
    return Depends(module_enabled(module))


router = APIRouter(tags=["design"])

#: Bitmaps only. An SVG is a document that can carry script, and it would be
#: served from our own origin.
#: What can go INTO an email. Bitmaps only — an email client will not render
#: anything else, and an SVG is a script vector in disguise.
ALLOWED_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}

#: What can be handed to the designer as a REFERENCE. These are never embedded
#: in an email; they are shown to the model so "make it like this" can be a
#: picture instead of a paragraph.
REFERENCE_MIME = dict(ALLOWED_MIME) | {"application/pdf": "pdf"}
MAX_ASSET_BYTES = 4 * 1024 * 1024
MAX_ASSETS = 40

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL DEFAULT '',
  mime       TEXT NOT NULL,
  bytes      BLOB NOT NULL,
  size       INTEGER NOT NULL DEFAULT 0,
  note       TEXT NOT NULL DEFAULT '',
  is_reference INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
"""

#: Added to `templates` after the first release.
TEMPLATE_COLUMNS = {
    "html": "TEXT NOT NULL DEFAULT ''",
    "subject_en": "TEXT NOT NULL DEFAULT ''",
    "subject_fa": "TEXT NOT NULL DEFAULT ''",
    "is_default": "INTEGER NOT NULL DEFAULT 0",
    "source": "TEXT NOT NULL DEFAULT 'manual'",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}


def migrate() -> None:
    have = {r["name"] for r in db.query("PRAGMA table_info(templates)")}
    for column, ddl in TEMPLATE_COLUMNS.items():
        if column not in have:
            db.execute(f"ALTER TABLE templates ADD COLUMN {column} {ddl}")

    # References arrived after assets did, and an install that predates them
    # would otherwise fail on first read of the column.
    have = {r["name"] for r in db.query("PRAGMA table_info(assets)")}
    if "is_reference" not in have:
        db.execute("ALTER TABLE assets ADD COLUMN is_reference INTEGER NOT NULL DEFAULT 0")


# ================================================================== schemas


class AssetIn(Body):
    """Uploaded as base64 rather than multipart.

    The panel already sends JSON with a bearer token for everything else, and
    an image small enough to put in an email is small enough to base64.
    """
    name: str = ""
    mime: str
    data: str
    note: str = ""
    #: A reference is design input, never email content. It widens the accepted
    #: types to include PDF and keeps the file out of the image picker.
    reference: bool = False


class TemplateGenerateIn(Body):
    brief: str
    assets: list[str] = []
    facts: str = ""
    lang: str = "en"
    palette: str = ""
    #: Asset ids to LOOK at rather than embed — a screenshot of a Pinterest
    #: board, a PDF of a brand guide, a competitor's email.
    references: list[str] = []
    #: What the operator wants taken from them, in their own words.
    referenceNote: str = ""


class TemplateSaveIn(Body):
    name: str = ""
    html: str = ""
    subject: str = ""
    category: str = "promo"


# =================================================================== assets


@router.get("/assets", dependencies=[_needs("templates")])
def list_assets(_: Principal = Depends(requires("content.edit"))) -> list[dict]:
    """Metadata only — the bytes are served one at a time."""
    rows = db.query("SELECT id, name, mime, size, note, is_reference, created_at "
                    "FROM assets ORDER BY created_at DESC")
    return [{"id": r["id"], "name": r["name"], "mime": r["mime"], "size": r["size"],
             "note": r["note"], "url": f"/api/assets/{r['id']}",
             "reference": bool(r["is_reference"]), "at": r["created_at"]} for r in rows]


@router.post("/assets", status_code=201, dependencies=[_needs("templates")])
def upload_asset(payload: AssetIn, principal: Principal = Depends(requires("content.edit"))) -> dict:
    allowed = REFERENCE_MIME if payload.reference else ALLOWED_MIME
    if payload.mime not in allowed:
        raise HTTPException(
            status_code=422,
            detail=("References may be an image or a PDF"
                    if payload.reference
                    else f"Only {', '.join(sorted(ALLOWED_MIME))} images are accepted"),
        )
    if db.scalar("SELECT COUNT(*) FROM assets", default=0) >= MAX_ASSETS:
        raise HTTPException(status_code=409, detail=f"This deployment holds {MAX_ASSETS} images already")

    raw = payload.data
    # browsers hand over a full data: URI; keep only the payload
    if "," in raw and raw.strip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="That image could not be decoded") from exc
    if not blob:
        raise HTTPException(status_code=422, detail="That image is empty")
    if len(blob) > MAX_ASSET_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"Images must be under {MAX_ASSET_BYTES // (1024 * 1024)}MB")

    aid = new_id("img")
    db.insert("assets", {"id": aid, "name": payload.name[:120], "mime": payload.mime,
                         "is_reference": 1 if payload.reference else 0,
                         "bytes": blob, "size": len(blob), "note": payload.note[:200],
                         "created_at": iso()})
    log(kind="human", actor=principal.id, action_en="uploaded an image",
        action_fa="یک تصویر بارگذاری کرد", target=aid, tone="info")
    return {"id": aid, "name": payload.name, "mime": payload.mime, "size": len(blob),
            "note": payload.note, "url": f"/api/assets/{aid}"}


@router.get("/assets/{asset_id}")
def serve_asset(asset_id: str) -> Response:
    """Served without a token on purpose.

    These URLs end up as `<img src>` in mail that has already been delivered;
    a recipient's mail client has no bearer token and never will. The id is a
    random 12-character string, which is what keeps the store private.
    """
    row = db.one("SELECT mime, bytes FROM assets WHERE id = ?", (asset_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="No such image")
    return Response(
        content=row["bytes"],
        media_type=row["mime"],
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


class AssetNoteIn(Body):
    note: str = ""


@router.patch("/assets/{asset_id}", dependencies=[_needs("templates")])
def describe_asset(asset_id: str, payload: AssetNoteIn,
                   _: Principal = Depends(requires("content.edit"))) -> dict:
    """Label a picture.

    This is the only thing the model ever learns about an image — it cannot see
    the file — so the caption is doing real work, and it is worth storing once
    rather than retyping on every generation.
    """
    if db.one("SELECT id FROM assets WHERE id = ?", (asset_id,)) is None:
        raise HTTPException(status_code=404, detail="No such image")
    db.update("assets", asset_id, {"note": payload.note[:200]})
    return {"id": asset_id, "note": payload.note[:200]}


@router.delete("/assets/{asset_id}", status_code=204, dependencies=[_needs("templates")])
def delete_asset(asset_id: str, _: Principal = Depends(requires("content.edit"))) -> None:
    if db.one("SELECT id FROM assets WHERE id = ?", (asset_id,)) is None:
        raise HTTPException(status_code=404, detail="No such image")
    # An image still shown by a saved template must not vanish out from under it
    for row in db.query("SELECT id, html FROM templates WHERE html <> ''"):
        if asset_id in emailhtml.used_assets(row["html"]):
            raise HTTPException(status_code=409,
                                detail="That image is used by a template. Remove it there first.")
    db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))


# ================================================================ generate

TEMPLATE_SHAPE = """{
  "subject": "a subject line for this template",
  "html": "the complete email as a single HTML string",
  "notes": "one sentence on the layout you chose"
}"""


@router.post("/ai/template", dependencies=[_needs("templates")])
def generate_template(payload: TemplateGenerateIn,
                      principal: Principal = Depends(requires("content.edit"))) -> dict:
    """Write an email template around the operator's own pictures and facts."""
    if not payload.brief.strip():
        raise HTTPException(status_code=422, detail="Describe the email you want")
    if not deployment.get().get("ai_key"):
        raise HTTPException(status_code=400, detail="This installation has no AI key yet")

    picked = []
    for aid in payload.assets[:8]:
        row = db.one("SELECT id, name, note, mime FROM assets "
                     "WHERE id = ? AND is_reference = 0", (aid,))
        if row is not None:
            picked.append({"url": f"/api/assets/{row['id']}",
                           "describes": row["note"] or row["name"] or "an image"})

    try:
        daily, monthly = deployment.caps()
        budget.check(daily, monthly)
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    # References are LOOKED at, not embedded. A PDF cannot be shown to the
    # model as an image, so its pages are not sent — only the operator's note
    # about it, which is said plainly in the UI rather than pretended away.
    reference_images, skipped_pdfs = [], 0
    for aid in payload.references[:4]:
        row = db.one("SELECT id, mime, bytes FROM assets WHERE id = ?", (aid,))
        if row is None:
            continue
        if row["mime"] == "application/pdf":
            # A PDF cannot be shown to the model as a picture. It is kept and
            # the operator is told it was not read, rather than being left to
            # assume it was.
            skipped_pdfs += 1
            continue
        encoded = base64.b64encode(row["bytes"]).decode()
        reference_images.append(f"data:{row['mime']};base64,{encoded}")

    system = emaildesign.brief(
        lang=payload.lang,
        palette=payload.palette,
        images=picked,
        reference_note=payload.referenceNote.strip(),
        has_reference_images=bool(reference_images),
    )

    user = payload.brief.strip()
    if payload.facts.strip():
        user += "\n\nFacts that must appear, exactly as given:\n" + payload.facts.strip()

    try:
        out = brain.complete_json_grounded(
            system_extra=system,
            user=user,
            shape=TEMPLATE_SHAPE,
            # A designed email is a whole HTML document — head, media queries,
            # a dark-mode block, a VML button and the tables around them. It
            # does not fit in the chat-sized per-request cap, so this task
            # declares what it needs; HARD_MAX_TOKENS and the daily ledger
            # still bind.
            max_tokens=8000,
            token_floor=8000,
            temperature=0.6,
            images=reference_images,
        )
    except AIUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    budget.record(out.get("_usage") or 0)

    html = emailhtml.sanitize(str(out.get("html") or ""))
    if not html:
        raise HTTPException(status_code=502, detail="The model returned no usable HTML")

    log(kind="agent", actor=deployment.get()["agent_name"], action_en="designed an email template",
        action_fa="یک قالب ایمیل طراحی کرد", target="templates", tone="info")
    return {"html": html, "subject": str(out.get("subject") or "").strip(),
            "notes": str(out.get("notes") or "").strip(),
            "issues": emailhtml.lint(html), "usedAssets": emailhtml.used_assets(html),
            # Said, not swallowed: a PDF reference was accepted and stored but
            # its pages were not shown to the model.
            "pdfsNotRead": skipped_pdfs}


# ================================================================ templates


@router.get("/templates/default")
def read_default(_: Principal = Depends(current_principal)) -> dict:
    """Which template every campaign will be sent in, if any.

    Not gated on the templates module: a deployment can be handed a house style
    by its implementer without being sold the designer to change it.
    """
    house = emailhtml.default_template(db)
    if house is None:
        return {"id": None, "name": "", "wraps": False}
    return {
        "id": house["id"],
        "name": house["name"],
        # a template with no content slot is a finished email, not a wrapper
        "wraps": emailhtml.CONTENT_SLOT in (house["html"] or ""),
    }


@router.post("/templates/starter", status_code=201, dependencies=[_needs("templates")])
def create_starter(principal: Principal = Depends(requires("content.edit"))) -> dict:
    """Install the house template that ships with the product.

    Here so that a deployment with no AI key is not stuck sending bare
    paragraphs, and so the first thing an operator sees in the designer is a
    finished email rather than an empty canvas. It is a normal template once
    created — editable, replaceable, deletable.
    """
    d = deployment.get()
    html = emaildesign.starter(d.get("default_lang") or "en", d.get("accent") or "#7ba3cd")
    tid = new_id("tpl")
    with db.transaction():
        db.insert("templates", {
            "id": tid, "name_en": "House style", "name_fa": "قالب خانگی",
            "category": "newsletter", "accent": d.get("accent") or "#7ba3cd",
            "html": html, "created_at": iso(),
        })
        log(kind="human", actor=principal.id, action_en="installed the house template",
            action_fa="قالب خانگی نصب شد", target=tid, tone="good")
    return {"id": tid, "html": html, "issues": emailhtml.lint(html)}


@router.get("/templates/{template_id}/html", dependencies=[_needs("templates")])
def template_html(template_id: str, _: Principal = Depends(current_principal)) -> dict:
    row = db.one("SELECT * FROM templates WHERE id = ?", (template_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="No such template")
    html = row["html"] or ""
    return {"id": row["id"], "html": html, "issues": emailhtml.lint(html)}


@router.put("/templates/{template_id}", dependencies=[_needs("templates")])
def save_template(template_id: str, payload: TemplateSaveIn,
                  principal: Principal = Depends(requires("content.edit"))) -> dict:
    """Save an edit. The HTML is sanitised again, because a human typed it."""
    row = db.one("SELECT * FROM templates WHERE id = ?", (template_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="No such template")

    data: dict = {"updated_at": iso()}
    if payload.name:
        data["name_en"] = payload.name
        data["name_fa"] = payload.name
    if payload.subject:
        data["subject_en"] = payload.subject
        data["subject_fa"] = payload.subject
    if payload.html:
        data["html"] = emailhtml.sanitize(payload.html)
    if payload.category:
        data["category"] = payload.category

    db.update("templates", template_id, data)
    saved = db.one("SELECT * FROM templates WHERE id = ?", (template_id,))
    log(kind="human", actor=principal.id, action_en="edited an email template",
        action_fa="یک قالب ایمیل را ویرایش کرد", target=template_id, tone="info")
    return {"id": saved["id"], "html": saved["html"], "issues": emailhtml.lint(saved["html"] or "")}


@router.post("/templates/{template_id}/default", dependencies=[_needs("templates")])
def make_default(template_id: str, principal: Principal = Depends(requires("content.edit"))) -> dict:
    """Make this the house style — the one every campaign starts from.

    Exactly one template can hold it, so the flag is cleared everywhere else in
    the same transaction rather than left for a later query to disambiguate.
    """
    row = db.one("SELECT * FROM templates WHERE id = ?", (template_id,))
    if row is None:
        raise HTTPException(status_code=404, detail="No such template")
    if not (row["html"] or "").strip():
        raise HTTPException(status_code=409, detail="That template has no content yet")

    with db.transaction():
        db.execute("UPDATE templates SET is_default = 0")
        db.execute("UPDATE templates SET is_default = 1 WHERE id = ?", (template_id,))
    log(kind="human", actor=principal.id, action_en="set the default email template",
        action_fa="قالب پیش‌فرض ایمیل را تعیین کرد", target=template_id, tone="good")
    return {"ok": True, "id": template_id}
