"""Validated request/response contracts, shared by Swagger and generated OpenAPI."""

from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def to_utc(value: datetime):
    return value.astimezone(UTC)


Timestamp = Annotated[AwareDatetime, AfterValidator(to_utc)]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    ),
]
Personality = Literal["warm", "direct", "playful"]
CompanionMode = Literal["off", "buddy", "mentor", "girlfriend"]
AccountLevel = Literal["university", "k12"]
SourceKind = Literal["syllabus", "material"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfilePatch(Input):
    name: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
        ]
        | None
    ) = None
    timezone: str | None = None
    personality: Personality | None = None
    companion_mode: CompanionMode | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError(
                    "Use an IANA timezone, e.g. Asia/Ho_Chi_Minh"
                ) from None
        return value

    @model_validator(mode="after")
    def no_explicit_nulls(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Profile fields cannot be null")
        return self


class Register(Input):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    # Collected now for the 18+ companion gate (week 3) and K-12 accounts (week 4).
    birth_year: int
    account_level: AccountLevel = "university"
    timezone: str = "Asia/Ho_Chi_Minh"

    @field_validator("password")
    @classmethod
    def strong_password(cls, value):
        if not (any(c.isalpha() for c in value) and any(c.isdigit() for c in value)):
            raise ValueError("Password needs at least one letter and one digit")
        return value

    @field_validator("birth_year")
    @classmethod
    def plausible_birth_year(cls, value):
        if not 1900 <= value <= date.today().year:
            raise ValueError("birth_year must be between 1900 and the current year")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return ProfilePatch.valid_timezone(value)


class Login(Input):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class UserOut(Output):
    id: str
    email: str
    name: str
    timezone: str
    personality: Personality
    role: str
    account_level: AccountLevel
    birth_year: int | None
    companion_mode: CompanionMode


class TokenOut(Output):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class GoalCreate(Input):
    title: Title
    description: str = Field(default="", max_length=4000)
    due_at: Timestamp | None = None


class GoalPatch(Input):
    title: Title | None = None
    description: str | None = Field(default=None, max_length=4000)
    due_at: Timestamp | None = None

    @model_validator(mode="after")
    def no_null_text(self):
        if any(
            getattr(self, key) is None for key in self.model_fields_set - {"due_at"}
        ):
            raise ValueError("Title and description cannot be null")
        return self


class GoalOut(Output):
    id: str
    title: str
    description: str
    due_at: datetime | None


class TaskCreate(Input):
    title: Title
    description: str = Field(default="", max_length=4000)
    duration_minutes: int = Field(ge=1, le=10080)
    priority: int = Field(default=2, ge=1, le=3, description="1 is highest priority")
    due_at: Timestamp
    goal_id: str | None = None
    team_id: str | None = None
    assignee_id: str | None = None


class TaskPatch(Input):
    title: Title | None = None
    description: str | None = Field(default=None, max_length=4000)
    duration_minutes: int | None = Field(default=None, ge=1, le=10080)
    priority: int | None = Field(default=None, ge=1, le=3)
    due_at: Timestamp | None = None
    goal_id: str | None = None
    status: Literal["pending", "cancelled"] | None = None

    @model_validator(mode="after")
    def no_null_required_fields(self):
        if any(
            getattr(self, key) is None for key in self.model_fields_set - {"goal_id"}
        ):
            raise ValueError("Only goal_id can be null")
        return self


class TaskOut(Output):
    id: str
    owner_id: str
    assignee_id: str
    goal_id: str | None
    team_id: str | None
    title: str
    description: str
    duration_minutes: int
    completed_minutes: int
    priority: int
    due_at: datetime
    status: str
    roadmap_node_id: str | None = None


class TimeRange(Input):
    starts_at: Timestamp
    ends_at: Timestamp

    @model_validator(mode="after")
    def ordered(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if (self.ends_at - self.starts_at).days > 90:
            raise ValueError("A time range cannot exceed 90 days")
        if any(
            value.second or value.microsecond
            for value in (self.starts_at, self.ends_at)
        ):
            raise ValueError("Use whole-minute timestamps")
        return self


class AvailabilityPut(Input):
    windows: list[TimeRange] = Field(max_length=200)


class WindowOut(Output):
    id: str
    starts_at: datetime
    ends_at: datetime


class BusyCreate(TimeRange):
    title: Title = "Busy"


class BusyOut(WindowOut):
    title: str


class PlanRequest(TimeRange):
    max_session_minutes: int = Field(default=60, ge=5, le=240)
    min_session_minutes: int = Field(default=15, ge=1, le=120)
    daily_limit_minutes: int = Field(default=240, ge=1, le=1440)
    commit: bool = False

    @model_validator(mode="after")
    def session_bounds(self):
        if self.min_session_minutes > self.max_session_minutes:
            raise ValueError("min_session_minutes cannot exceed max_session_minutes")
        return self


class EntryOut(Output):
    id: str
    task_id: str
    starts_at: datetime
    ends_at: datetime
    status: str
    actual_minutes: int


class ProposedEntry(Output):
    task_id: str
    starts_at: datetime
    ends_at: datetime


class Unscheduled(Output):
    task_id: str
    minutes: int
    reason: str


class PlanOut(Output):
    committed: bool
    expired_sessions: int = 0
    entries: list[ProposedEntry]
    unscheduled: list[Unscheduled]
    # Local Mondays of weeks that ran out of hours before a deadline (spec 10.4).
    overloaded_weeks: list[date] = Field(default_factory=list)


class CheckIn(Input):
    status: Literal["completed", "missed"]
    actual_minutes: int | None = Field(default=None, ge=0, le=240)


class TeamCreate(Input):
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


class TeamOut(Output):
    id: str
    name: str
    owner_id: str


class InviteCreate(Input):
    email: Email


class ShareTask(Input):
    team_id: str
    assignee_id: str | None = None


class MemberOut(Output):
    id: str
    name: str


class InvitationOut(Output):
    id: str
    team_id: str
    team_name: str
    email: str
    accepted: bool


class InvitationCreated(InvitationOut):
    code: str = Field(
        description="Shown once. The owner sends it to the invitee, who must enter "
        "it to join; re-inviting the same email issues a new code."
    )


class InvitationAccept(Input):
    code: str = Field(min_length=1, max_length=100)


class CoordinateRequest(TimeRange):
    duration_minutes: int = Field(default=60, ge=1, le=240)


class CommonSlot(Output):
    starts_at: datetime
    ends_at: datetime


class NotificationOut(Output):
    id: str
    entry_id: str | None
    message: str
    read: bool
    created_at: datetime


class ChatRequest(Input):
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    mood: Literal["neutral", "happy", "stressed", "tired"] = "neutral"


class ChatOut(Output):
    reply: str
    provider: Literal["llm", "offline"]
    fallback_reason: str | None = None


class MessageOut(Output):
    id: str
    role: str
    content: str
    created_at: datetime


class ReportOut(Output):
    start_date: date
    end_date: date
    total_tasks: int
    completed_tasks: int
    planned_minutes: int
    completed_minutes: int
    missed_sessions: int
    completion_percent: int


class CourseCreate(Input):
    title: Title
    level: AccountLevel = "university"
    language: Literal["vi", "en"] = "vi"


class CourseOut(Output):
    id: str
    title: str
    level: str


class SourceOut(Output):
    id: str
    file_name: str
    page: int
    text: str
    kind: SourceKind


class UploadOut(Output):
    file_name: str
    pages: int
    kind: SourceKind
    status: Literal["processed"]
    warning: Literal["scanned_pdf"] | None = None


class ConceptOut(Output):
    id: str
    slug: str
    title: str
    summary: str
    bloom_level: str
    source_pages: list[int]
    confirmed: bool


class PrereqOut(Output):
    parent_id: str
    child_id: str
    kind: Literal["strict", "soft"]
    confidence: float


class ItemOut(Output):
    id: str
    type: str
    prompt: str
    choices: list[str]
    answer: str
    rubric: list[str]
    source_id: str
    page: int
    file_name: str
    status: str


class ConceptGraphOut(Output):
    concepts: list[ConceptOut]
    prereqs: list[PrereqOut]


# ---------------------------------------------------------------------------
# Core loop: syllabus -> roadmap -> schedule (issue #63).
# ---------------------------------------------------------------------------


class FlexibleInput(BaseModel):
    """Accept the schema/spec aliases without rejecting forward-compatible fields."""

    model_config = ConfigDict(extra="ignore")


class LearningOutcomeIn(FlexibleInput):
    code: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=4000)
    text: str | None = Field(default=None, max_length=4000)
    bloom_level: str | None = Field(default=None, max_length=50)


class AssessmentIn(FlexibleInput):
    name: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    weight: float | str | None = None
    due_week: int | str | None = None
    due: str | None = None
    kind: str | None = None


class SyllabusIn(FlexibleInput):
    raw_text: str | None = None
    text: str | None = None
    learning_outcomes: list[LearningOutcomeIn | str] = Field(default_factory=list)
    outcomes: list[LearningOutcomeIn | str] = Field(default_factory=list)
    assessments: list[AssessmentIn | str] = Field(default_factory=list)
    parsed: dict[str, Any] | None = None
    syllabus_id: str | None = None
    title: str | None = None
    version: int | None = None
    pages: int | None = None
    status: str | None = None


class SyllabusParseIn(BaseModel):
    """Preview one uploaded syllabus or pasted text before saving/confirmation."""

    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, min_length=1, max_length=120000)
    file_name: str | None = Field(default=None, min_length=1, max_length=255)
    use_llm: bool = False


class RoadmapNodeIn(FlexibleInput):
    type: str | None = None
    kind: str | None = None
    title: str | None = None
    description: str | None = None
    week: int | str | None = None
    duration_minutes: int | str | None = None
    est_minutes: int | str | None = None
    duration: int | str | None = None
    due_at: datetime | None = None
    covers: list[str] | str | None = None
    outcomes: list[str] = Field(default_factory=list)
    status: str | None = None


class RoadmapGenerateIn(FlexibleInput):
    syllabus_id: str | None = None
    title: str | None = None
    nodes: list[RoadmapNodeIn] = Field(default_factory=list)


class RoadmapScheduleIn(FlexibleInput):
    """Sessions always fit availability minus busy blocks (spec 10.4); a weekly budget
    is not enforced yet, so ``weekly_minutes`` is ignored like any unknown field."""

    # At least one 25-minute session a day (spec 10.3.4).
    max_daily_minutes: int = Field(default=120, ge=25, le=1440)
    starts_at: Timestamp | None = None


class LearningOutcomeOut(Output):
    id: str
    syllabus_id: str
    code: str
    description: str
    bloom_level: str


class AssessmentOut(Output):
    id: str
    syllabus_id: str
    name: str
    weight: float
    due_week: int | None


class SyllabusOut(Output):
    id: str
    syllabus_id: str
    course_id: str
    raw_text: str
    created_at: datetime
    learning_outcomes: list[LearningOutcomeOut] = Field(default_factory=list)
    assessments: list[AssessmentOut] = Field(default_factory=list)


class RoadmapNodeOut(Output):
    id: str
    roadmap_id: str
    type: str
    kind: str | None = None
    title: str
    week: int | None = None
    duration_minutes: int | None = None
    est_minutes: int | None = None
    due_at: datetime | None = None
    covers: list[str] = Field(default_factory=list)


class RoadmapOut(Output):
    id: str
    roadmap_id: str
    course_id: str
    user_id: str
    title: str
    created_at: datetime
    nodes: list[RoadmapNodeOut] = Field(default_factory=list)


class RoadmapScheduleOut(Output):
    roadmap_id: str
    tasks: list[TaskOut] = Field(default_factory=list)
    sessions: list[EntryOut] = Field(default_factory=list)
    entries: list[EntryOut] = Field(default_factory=list)
    unscheduled: list[Unscheduled] = Field(default_factory=list)
    overloaded_weeks: list[date] = Field(default_factory=list)


class JobOut(Output):
    id: str
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    attempts: int
    result: Any = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class CostTotals(Output):
    searches: int
    cache_hits: int
    llm_calls: int
    llm_calls_today: int  # against the LLM vendor's daily quota
    llm_cost_usd: float
    search_cost_usd: float
    cost_usd: float
    cost_per_search_usd: float


class NodeCost(Output):
    node_id: str | None  # None once the node's roadmap is deleted
    node_title: str
    searches: int
    cache_hits: int
    llm_calls: int
    llm_cost_usd: float
    search_cost_usd: float
    cost_usd: float
    last_search_at: datetime


class ProviderUsage(Output):
    provider: str
    calls: int
    errors: int
    calls_today: int  # against the provider's daily quota
    avg_latency_ms: float
    max_latency_ms: int
    cost_usd: float


class DailyCost(Output):
    day: date
    searches: int
    cost_usd: float


class CostReport(Output):
    days: int
    since: datetime
    totals: CostTotals
    nodes: list[NodeCost]  # most expensive first
    providers: list[ProviderUsage]
    daily: list[DailyCost]


# --- Resources & Feedback (issue #65, spec 8.5-8.7) -------------------------


class ResourceSearchOut(Output):
    run_id: str


class ResourceItemOut(Output):
    id: str
    rank: int
    title: str
    url: str
    domain: str
    format: str
    language: str = "en"
    duration_min: int | None = None
    is_free: bool = True
    score: float
    breakdown: dict[str, float] = Field(default_factory=dict)
    reason: str = ""
    evidence_quote: str = ""
    pinned: bool = False


class NodeResourcesOut(Output):
    status: Literal["searching", "ready", "insufficient"]
    resources: list[ResourceItemOut] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ResourceFeedbackIn(Input):
    node_id: str
    helpful: bool
    reason: str | None = None


class ResourceFeedbackOut(Output):
    status: Literal["ok"] = "ok"
    replacement: ResourceItemOut | None = None


# --- Replan (issue #65, spec 8.4, 10.5) -------------------------------------


class RoadmapReplanIn(Input):
    approve: bool = False
    commit: bool = False
    max_daily_minutes: int | None = None
    starts_at: Timestamp | None = None


class PlanDiffOut(Output):
    moved: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)


class RoadmapReplanOut(Output):
    roadmap_id: str
    diff: PlanDiffOut
    committed: bool
    sessions: list[ProposedEntry] = Field(default_factory=list)
