"""The five cited sections returned by the syllabus extractor (spec 9.1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class CitedValue(Record):
    value: StrictStr | StrictInt | float
    source_page: StrictInt | None = Field(default=None, ge=1)


class CourseInfo(Record):
    code: CitedValue | None = None
    title: CitedValue | None = None
    credits: CitedValue | None = None
    term_start: CitedValue | None = None
    term_end: CitedValue | None = None
    language: CitedValue | None = None


class CitedRecord(Record):
    source_page: StrictInt | None = Field(default=None, ge=1)


class CitedOutcome(CitedRecord):
    code: StrictStr
    text: StrictStr
    bloom_level: StrictStr = "understand"


class CitedWeek(CitedRecord):
    week: StrictInt = Field(ge=1, le=52)
    topics: list[StrictStr]
    readings: list[StrictStr] = Field(default_factory=list)
    estimated: bool = False


class CitedAssessment(CitedRecord):
    title: StrictStr
    kind: StrictStr = "other"
    weight: float | None = Field(default=None, ge=0, le=100)
    due: StrictStr | None = None


class CitedTextbook(CitedRecord):
    title: StrictStr
    authors: StrictStr | None = None
    required: bool | None = None


class ParsedSyllabus(Record):
    course: CourseInfo = Field(default_factory=CourseInfo)
    outcomes: list[CitedOutcome] = Field(default_factory=list)
    weeks: list[CitedWeek] = Field(default_factory=list)
    assessments: list[CitedAssessment] = Field(default_factory=list)
    textbooks: list[CitedTextbook] = Field(default_factory=list)


SYLLABUS_SCHEMA = ParsedSyllabus.model_json_schema()
