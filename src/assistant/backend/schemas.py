"""Validated request/response contracts, shared by Swagger and generated OpenAPI."""

from datetime import UTC, date, datetime
from typing import Annotated, Literal
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


class CourseOut(Output):
    id: str
    title: str
    level: str


class SourceOut(Output):
    id: str
    file_name: str
    page: int
    text: str


class UploadOut(Output):
    file_name: str
    pages: int
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
