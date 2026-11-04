"""Syllabus: parses a syllabus into outcomes, weeks and assessments (spec 6.1, 9).

``extract`` reads uploaded pages with the LLM (issue #59); ``parse`` normalizes what the
API receives once the user has reviewed it.
"""

from app.syllabus.checks import SyllabusWarning, check_syllabus
from app.syllabus.extract import NotASyllabus, SyllabusDraft, extract_syllabus
from app.syllabus.parse import AssessmentItem, Outcome, SyllabusParts, parse_syllabus

__all__ = [
    "AssessmentItem",
    "NotASyllabus",
    "Outcome",
    "SyllabusDraft",
    "SyllabusParts",
    "SyllabusWarning",
    "check_syllabus",
    "extract_syllabus",
    "parse_syllabus",
]
