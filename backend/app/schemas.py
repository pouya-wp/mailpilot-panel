"""Request bodies.

Only INPUT is modelled with pydantic. Responses are plain dicts built by
`serial.py`, because their shape is dictated by what the React app already
consumes — wrapping that in a second set of models would mean maintaining the
same field list twice and would buy nothing at runtime.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Lang = dict[str, str] | str


class Body(BaseModel):
    # reject unknown keys instead of silently dropping them: a client that
    # sends `titel` should be told, not left wondering why nothing changed
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- auth


class LoginIn(Body):
    email: str
    password: str


class RefreshIn(Body):
    refresh_token: str


class PasswordIn(Body):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


# ---------------------------------------------------------------- campaigns


class CampaignIn(Body):
    name: Lang
    subject: Lang | None = None
    body: Lang | None = None
    type: Literal["broadcast", "drip", "transactional", "agent", "abtest"] = "broadcast"
    agent: str | None = None
    segment: str | None = None
    scheduled_for: str | None = None


class CampaignPatch(Body):
    name: Lang | None = None
    subject: Lang | None = None
    body: Lang | None = None
    type: Literal["broadcast", "drip", "transactional", "agent", "abtest"] | None = None
    agent: str | None = None
    segment: str | None = None
    scheduled_for: str | None = None


class SendIn(Body):
    mode: Literal["now", "schedule", "optimal"] = "now"
    scheduled_for: str | None = None


# ---------------------------------------------------------------- contacts


class ContactIn(Body):
    email: EmailStr
    name: Lang | None = None
    status: Literal["subscribed", "unsubscribed", "bounced", "pending"] = "subscribed"
    tags: list[str] = Field(default_factory=list)
    country: str = ""
    source: str = "api"

    @field_validator("tags")
    @classmethod
    def _cap_tags(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t.strip()][:20]


class ContactPatch(Body):
    name: Lang | None = None
    status: Literal["subscribed", "unsubscribed", "bounced", "pending"] | None = None
    tags: list[str] | None = None
    country: str | None = None
    score: int | None = Field(default=None, ge=0, le=100)


class ImportIn(Body):
    """A contact list, as a paste or as an uploaded file.

    `csv` is the original paste path. `data` is a base64 file — CSV or XLSX —
    and `mapping` says which of its columns is which of our fields, which is
    what makes an export with headers in another language importable at all.
    """

    csv: str = ""
    data: str = ""
    filename: str = ""
    mapping: dict[str, str] = Field(default_factory=dict)
    default_tags: list[str] = Field(default_factory=list)


class ImportAnalyseIn(Body):
    data: str
    filename: str = ""


# ---------------------------------------------------------------- agents


class AgentIn(Body):
    name: Lang
    role: Lang | None = None
    emoji: str = "🤖"
    model: str = "claude-opus-5"
    autonomy: Literal["suggest", "approve", "full"] = "approve"
    instructions: str = ""
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    budget: int = Field(default=100, ge=1, le=10000)
    temperature: float = Field(default=0.5, ge=0, le=1)


class AgentPatch(Body):
    name: Lang | None = None
    role: Lang | None = None
    model: str | None = None
    autonomy: Literal["suggest", "approve", "full"] | None = None
    status: Literal["active", "paused"] | None = None
    instructions: str | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    budget: int | None = Field(default=None, ge=1, le=10000)
    temperature: float | None = Field(default=None, ge=0, le=1)


# ---------------------------------------------------------------- segments


class Rule(Body):
    field: str
    op: str
    value: str


class SegmentIn(Body):
    name: Lang
    emoji: str = "🎯"
    #: "everyone" is the only way to build a group with no rules. An empty rule
    #: list on its own is refused, because a group someone forgot to describe
    #: used to silently mean the entire contact table.
    match: Literal["all", "any", "everyone"] = "all"
    rules: list[Rule] = Field(default_factory=list)


class SegmentPatch(Body):
    name: Lang | None = None
    emoji: str | None = None
    match: Literal["all", "any", "everyone"] | None = None
    rules: list[Rule] | None = None
    live: bool | None = None


# ---------------------------------------------------------------- inbox


class ReplyIn(Body):
    text: Lang | None = None
    send: bool = True


class AssignIn(Body):
    user_id: str | None = None


# ---------------------------------------------------------------- misc


class SuppressionIn(Body):
    email: EmailStr
    reason: Literal["unsub", "bounce", "complaint", "manual"] = "manual"


class DomainIn(Body):
    domain: str
    dedicated: bool = False


class InviteIn(Body):
    email: EmailStr
    role: Literal["admin", "editor", "analyst", "viewer"] = "editor"
    name: Lang | None = None


class RolePatch(Body):
    role: Literal["owner", "admin", "editor", "analyst", "viewer"]


class ApiKeyIn(Body):
    name: Lang
    scopes: list[str] = Field(default_factory=lambda: ["analytics:read"])


class WebhookIn(Body):
    url: str
    events: list[str] = Field(default_factory=list)


class WebhookPatch(Body):
    url: str | None = None
    events: list[str] | None = None
    on: bool | None = None


class IntegrationPatch(Body):
    on: bool


class SettingsPatch(Body):
    name: str | None = None
    timezone: str | None = None
    default_lang: Literal["en", "fa"] | None = None
    from_name: str | None = None
    from_email: EmailStr | None = None
    reply_to: EmailStr | None = None
    footer: str | None = None
    # Down to 1/hour on purpose: the whole point of the control is the
    # slow end, and it is only meaningful now the sender obeys it.
    throttle_per_hour: int | None = Field(default=None, ge=1, le=5_000_000)
    quiet_hours: bool | None = None
    quiet_from: str | None = None
    quiet_to: str | None = None
    default_model: str | None = None
    creativity: int | None = Field(default=None, ge=0, le=100)
    auto_approve: bool | None = None
    gdpr: bool | None = None
    retention_months: int | None = None
    notif: dict[str, bool] | None = None


class BrandVoiceIn(Body):
    axes: list[dict[str, Any]] | None = None
    banned: list[str] | None = None
    notes: str | None = None


class KbSourceIn(Body):
    name: Lang
    type: Literal["web", "file", "app", "internal"] = "file"


class TemplateIn(Body):
    name: Lang
    category: Literal["promo", "newsletter", "lifecycle", "transactional"] = "promo"
    accent: str = "#7ba3cd"
    #: set when the template comes straight out of the designer
    html: str = ""
    subject: str = ""
    source: Literal["manual", "ai"] = "manual"


class JourneyIn(Body):
    name: Lang
    trigger: Lang
    agent: str | None = None


class StepIn(Body):
    type: Literal["email", "wait", "branch", "agent", "tag", "webhook", "goal"]
    label: Lang
    position: int | None = None


class ExperimentIn(Body):
    name: Lang
    metric: Literal["openRate", "clickRate", "revenue"] = "openRate"
    auto_promote: bool = True
    variants: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------- ai


class ComposeIn(Body):
    brief: str = ""
    goal: Literal["awareness", "conversion", "retention", "winback", "nurture"] = "conversion"
    tone: Literal["friendly", "professional", "playful", "urgent", "luxury"] = "friendly"
    length: Literal["short", "medium", "long"] = "medium"
    lang: Literal["en", "fa"] = "en"
    emoji: bool = True
    personalize: bool = True
    creativity: int = Field(default=65, ge=0, le=100)
    segment: str | None = None
    agent: str | None = None


class SegmentAskIn(Body):
    prompt: str


class AskIn(Body):
    """One box, one sentence. Everything the old composer asked for in five
    controls, the agent now infers from this."""
    message: str
    lang: Literal["en", "fa"] = "en"
    # the last few turns, so a follow-up like "make it shorter" has a referent
    history: list[dict] = Field(default_factory=list)


class ResearchIn(Body):
    query: str
    lang: Literal["en", "fa"] = "en"
