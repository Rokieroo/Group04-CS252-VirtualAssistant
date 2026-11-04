"""Syllabus: parses a syllabus into outcomes, weeks and assessments (spec 6.1, 9).

``extract`` reads uploaded pages with the LLM (issue #59); ``parse`` normalizes what the
API receives once the user has reviewed it.
"""

from app.syllabus.checks import SyllabusWarning, check_syllabus
from app.syllabus.extract import NotASyllabus, SyllabusDraft, extract_syllabus
from app.syllabus.parse import AssessmentItem, Outcome, SyllabusParts, parse_syllabus
from app.syllabus.preview import (
    InvalidSyllabusResponse,
    SyllabusPreview,
    preview_syllabus,
    validate_syllabus,
)

__all__ = [
    "AssessmentItem",
    "InvalidSyllabusResponse",
    "NotASyllabus",
    "Outcome",
    "SyllabusDraft",
    "SyllabusParts",
    "SyllabusPreview",
    "SyllabusWarning",
    "check_syllabus",
    "extract_syllabus",
    "parse_syllabus",
    "preview_syllabus",
    "validate_syllabus",
]
