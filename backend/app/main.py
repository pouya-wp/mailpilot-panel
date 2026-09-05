"""The application.

Mounted under `/api` so the Vite dev server's existing `/api` proxy reaches it
with no extra configuration, and so a production deployment can put the SPA and
the API on one origin behind nginx without a rewrite rule.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import db, mailer, messages
from .config import settings
from .routers import (
    agents,
    ai,
    analytics,
    audience,
    auth,
    campaigns,
    chats,
    design,
    google,
    research,
    setup,
    unsubscribe,
    workspace,
)
from .seed import bootstrap, ensure_default_segment, seed

log = logging.getLogger("mailpilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")
    db.init_db()
    # A fresh install comes up EMPTY — one owner account and nothing else. The
    # showroom data is opt-in (`run.py --demo`), because the first screen of a
    # customer's own panel should not be somebody else's campaigns.
    if settings.seed_demo_on_start:
        if seed():
            log.info("seeded DEMO data at %s", settings.db_path)
    elif bootstrap():
        log.info("created an empty installation at %s", settings.db_path)
    else:
        log.info("database already present at %s", settings.db_path)
    # Every install needs at least one audience or it cannot send at all — see
    # `ensure_default_segment`. Runs for existing installs too, because the ones
    # made before today are exactly the ones stuck with no group.
    if ensure_default_segment():
        log.info("created the Everyone group — this install had no audience")

    # Anything the previous process was half-way through sending resumes here.
    mailer.resume_on_start()
    yield
    db.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.docs else None,
    description=(
        "Backend for the MailPilot admin panel.\n\n"
        "Every human-readable name is returned as `{en, fa}` — the client picks "
        "the language, so switching it stays instant and client-side."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """A request id on every response, and a timing log.

    The id is what makes a support conversation tractable: the client can quote
    it, and it appears on both the log line and the error body.
    """
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("%s %s %s failed", rid, request.method, request.url.path)
        raise
    took = (time.perf_counter() - started) * 1000
    response.headers["X-Request-Id"] = rid
    if not request.url.path.endswith("/stream"):
        log.info("%s %s %s -> %s in %.1fms", rid, request.method, request.url.path,
                 response.status_code, took)
    return response


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    """Every deliberate refusal, in the language the panel is being read in.

    The messages are written in English at the raise site and translated
    here, so nothing in the routers has to know about languages. Anything
    with no translation goes out in English, which is what happened before
    this existed — a gap degrades, it does not break.

    `exc.headers` is carried through: a 401 that loses its
    `WWW-Authenticate` is a different response.
    """
    detail = messages.translate(exc.detail, request.headers.get("accept-language"))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "request_id": getattr(request.state, "request_id", "")},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """A validation failure names the field, so the client can point at it."""
    problems = [
        {"field": ".".join(str(p) for p in err["loc"][1:]) or "body", "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": messages.translate("The request body did not validate",
                                              request.headers.get("accept-language")),
                 "problems": problems,
                 "request_id": getattr(request.state, "request_id", "")},
    )


API = "/api"
app.include_router(setup.router, prefix=API)
app.include_router(auth.router, prefix=API)
app.include_router(campaigns.router, prefix=API)
app.include_router(audience.router, prefix=API)
app.include_router(agents.router, prefix=API)
app.include_router(analytics.router, prefix=API)
app.include_router(workspace.router, prefix=API)
app.include_router(ai.router, prefix=API)
app.include_router(design.router, prefix=API)
app.include_router(chats.router, prefix=API)
app.include_router(google.router, prefix=API)
app.include_router(research.router, prefix=API)
# NOT under /api: this is a link in an email, clicked by a recipient who
# has never heard of this panel, and it should look like a plain URL.
app.include_router(unsubscribe.router)


@app.get(f"{API}/health", tags=["meta"])
def health() -> dict:
    """Cheap enough for a load balancer, real enough to catch a broken DB."""
    try:
        db.scalar("SELECT 1")
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    return {
        "ok": ok,
        "name": settings.app_name,
        "version": settings.version,
        "seeded": bool(db.scalar("SELECT COUNT(*) FROM workspaces", default=0)) if ok else False,
    }


@app.get(f"{API}/meta", tags=["meta"])
def meta() -> dict:
    """Enumerations the client would otherwise hard-code twice."""
    return {
        "languages": ["en", "fa"],
        "campaignTypes": ["broadcast", "drip", "transactional", "agent", "abtest"],
        "campaignStatuses": ["draft", "scheduled", "running", "paused", "sent"],
        "contactStatuses": ["subscribed", "unsubscribed", "bounced", "pending"],
        "suppressionReasons": ["unsub", "bounce", "complaint", "manual"],
        "intents": ["interested", "question", "objection", "unsubscribe", "ooo"],
        "autonomy": ["suggest", "approve", "full"],
        "journeyStepTypes": ["email", "wait", "branch", "agent", "tag", "webhook", "goal"],
        "templateCategories": ["promo", "newsletter", "lifecycle", "transactional"],
        "integrationCategories": ["ecommerce", "crm", "data", "messaging", "ads", "ai"],
        "models": [
            {"value": "claude-opus-5", "label": "Claude Opus 5"},
            {"value": "claude-sonnet-5", "label": "Claude Sonnet 5"},
            {"value": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        ],
    }


# ================================================================ the panel
#
# In development the panel is served by Vite on another port and this block
# does nothing. In production the built files sit next to the API and are
# served by it, so the whole product is ONE process behind ONE route — which
# is what lets it live beside n8n under Traefik without a second web server
# and without a second certificate.
#
# Mounted LAST, on purpose: `/` would otherwise shadow every API route
# registered above it.

_WEB = Path(os.environ.get("MAILPILOT_WEB", "")) if os.environ.get("MAILPILOT_WEB") else None

if _WEB and _WEB.is_dir():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        """Serve a built file, or the app shell.

        The panel is hash-routed, so the server almost always sees exactly `/`.
        The fallback matters anyway: it is what stops a mistyped URL, or a
        bookmark from an older build, returning a bare 404 instead of the app.
        """
        # Anything under /api that got this far matched no route, and an API
        # path must answer like an API. Without this the shell was returned
        # with a 200 for every unmatched /api call — including a GET on a
        # POST-only endpoint — so a client asking for JSON got `<!doctype html>`
        # and a 200, its error handling never ran, and the failure surfaced as
        # an unrelated parse error somewhere further down.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such endpoint")

        candidate = (_WEB / full_path).resolve()
        # `resolve()` then containment check: without it, `..%2f..%2fetc/passwd`
        # walks out of the web root and serves whatever it lands on.
        if full_path and candidate.is_file() and candidate.is_relative_to(_WEB.resolve()):
            return FileResponse(candidate)
        return FileResponse(_WEB / "index.html")

    log.info("serving the panel from %s", _WEB)
