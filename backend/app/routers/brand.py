"""The Brand Information wizard's API.

Four routes: read the profile, save an answer, ask the website what it can
tell us, and take a suggestion.

THE ONLY RULE WORTH STATING TWICE. `PATCH /brand-profile` is the customer
answering a question and marks what it touches as confirmed. The analysis
route may only fill in fields that are NOT confirmed. Nothing here can
overwrite an answer the customer gave, which is what makes it safe to
offer analysis a second time on a profile someone has already edited.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import brain, brandprofile, budget, db, deployment
from ..ai_provider import AIUnavailable
from ..deps import Principal, current_principal, requires
from ..domain import log
from ..schemas import Body

router = APIRouter(tags=["brand"])


class ProfilePatch(Body):
    """One or more answers. Every field optional — the wizard saves one at a
    time, and a review screen may save several."""

    brand_name: str | None = None
    website_url: str | None = None
    business_summary: str | None = None
    offers: list[dict] | None = None
    ideal_customer_profile: str | None = None
    customer_pain_points: list[str] | None = None
    customer_outcomes: list[str] | None = None
    differentiators: list[str] | None = None
    proof_points: list[dict] | None = None
    preferred_cta: str | None = None
    forbidden_claims: list[str] | None = None
    brand_voice: list[str] | None = None
    current_step: int | None = None
    completed: bool | None = None


class AcceptSuggestion(Body):
    """Which suggested fields the reader chose to keep."""

    fields: list[str] = []


def _serialise(profile: dict) -> dict:
    out = dict(profile)
    out["completeness"] = brandprofile.completeness(profile)
    out["totalSteps"] = brandprofile.TOTAL_STEPS
    out["tones"] = brandprofile.TONES
    out["ctas"] = brandprofile.CTAS
    return out


@router.get("/brand-profile")
def read_profile(_: Principal = Depends(current_principal)) -> dict:
    return _serialise(brandprofile.get())


@router.patch("/brand-profile")
def update_profile(payload: ProfilePatch,
                   principal: Principal = Depends(requires("settings.write"))) -> dict:
    """Save what the customer just answered.

    Autosave calls this on every step, so it has to be cheap and it has to
    be safe to call with a single field. `exclude_unset` is what makes that
    true: sending only `brand_name` must not blank the other eleven.
    """
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        return _serialise(brandprofile.get())

    if "preferred_cta" in patch and patch["preferred_cta"]:
        if patch["preferred_cta"] not in brandprofile.CTAS:
            raise HTTPException(status_code=422, detail="That is not a call to action this product offers")

    was_complete = brandprofile.get()["completed"]
    profile = brandprofile.save(patch)

    if profile["completed"] and not was_complete:
        log(kind="human", actor=principal.id,
            action_en="completed the brand information profile",
            action_fa="اطلاعات برند را تکمیل کرد", target="brand", tone="good")
    return _serialise(profile)


@router.post("/brand-profile/analyze")
def analyze_website(principal: Principal = Depends(requires("settings.write"))) -> dict:
    """Read the customer's own website and propose answers.

    Proposes. The result is stored under `analysis.suggestions` and nothing
    is written into the profile itself, because a suggestion the customer
    has not seen is not an answer. `POST /brand-profile/analyze/accept` is
    where a suggestion becomes an answer, one field at a time.
    """
    profile = brandprofile.get()
    url = (profile.get("website_url") or "").strip()
    if not url:
        raise HTTPException(status_code=422, detail="Add a website address first")
    if not deployment.get().get("ai_key"):
        raise HTTPException(status_code=400, detail="This installation has no AI key yet")
    if not deployment.ai_settings().search_enabled:
        raise HTTPException(
            status_code=400,
            detail=("Reading your website needs web search, which is switched off "
                    "for this installation. Turn it on in Setup — without it there "
                    "is nothing to read and the answers would be invented."),
        )

    try:
        daily, monthly = deployment.caps()
        budget.check(daily, monthly)
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    try:
        out = brain.read_website(url=url)
    except AIUnavailable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    budget.record(out.get("_usage") or 0)

    from ..domain import iso

    suggestions = _clean_suggestions(out)
    analysis = {
        "last_analyzed_at": iso(),
        "confidence": out.get("analysis_confidence") or 0,
        "suggestions": suggestions,
        # Which of them would actually be applied. A suggestion for a field
        # the customer has already answered is shown as "we read this, and
        # we are not touching yours" rather than silently dropped.
        "appliesTo": [f for f in suggestions if f not in profile["confirmed"]],
    }
    profile = brandprofile.save({"analysis": analysis}, confirm=False)

    log(kind="agent", actor=deployment.get()["agent_name"],
        action_en=f"read {url} for brand information",
        action_fa=f"وب‌سایت {url} را برای اطلاعات برند خواند",
        target="brand", tone="info")
    return _serialise(profile)


@router.post("/brand-profile/analyze/accept")
def accept_suggestions(payload: AcceptSuggestion,
                       _: Principal = Depends(requires("settings.write"))) -> dict:
    """Take some of what the website said, as the customer's own answer."""
    profile = brandprofile.get()
    suggestions = (profile.get("analysis") or {}).get("suggestions") or {}
    wanted = [f for f in payload.fields if f in suggestions and f in brandprofile.FIELDS]
    if not wanted:
        raise HTTPException(status_code=422, detail="Nothing to apply")

    # Accepting IS confirming: the customer read it and chose it, so later
    # analysis must leave it alone exactly as if they had typed it.
    return _serialise(brandprofile.save({f: suggestions[f] for f in wanted}))


def _clean_suggestions(out: dict) -> dict:
    """Map the model's answer onto profile fields, dropping anything empty.

    Only the fields a website can honestly speak to. It cannot know what
    the business refuses to claim, and it must not guess a call to action.
    """
    pairs = [
        ("business_summary", "detected_business_summary"),
        ("offers", "detected_offers"),
        ("ideal_customer_profile", "detected_customer_types"),
        ("customer_outcomes", "detected_value_propositions"),
        ("differentiators", "detected_differentiators"),
        ("proof_points", "detected_proof"),
        ("brand_voice", "suggested_brand_voice"),
    ]
    found: dict = {}
    for field, key in pairs:
        value = out.get(key)
        if value in (None, "", [], {}):
            continue
        if field == "ideal_customer_profile" and isinstance(value, list):
            value = "، ".join(str(v) for v in value[:5])
        if field == "offers" and isinstance(value, list):
            value = [
                {"name": str(v.get("name") if isinstance(v, dict) else v)[:200],
                 "description": str(v.get("description") if isinstance(v, dict) else "")[:1000]}
                for v in value[:10]
            ]
        if field == "proof_points" and isinstance(value, list):
            value = [{"kind": "website", "text": str(v)[:1000]} for v in value[:10]
                     if str(v).strip()]
        if field == "brand_voice" and isinstance(value, list):
            value = [t for t in value if t in brandprofile.TONES][:6]
        if value:
            found[field] = value
    return found
