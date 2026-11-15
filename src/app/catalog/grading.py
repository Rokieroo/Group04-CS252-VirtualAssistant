"""Mark a learner's answer against the answer the source itself prints (#115).

Nothing here writes an answer. An exercise is marked only when its source gives
a short key: an option, a number or a phrase of a few words. A longer key is a
worked solution, and proofs and programs have no single right wording, so those
are shown to the learner to compare with their own (self-check).
"""

import re
import unicodedata
from fractions import Fraction

from app.catalog.exercises import ANSWER, collapse

SHORT_KEY_WORDS = 4  # a longer key is a worked solution, not a phrase to match
NEVER_MARKED = {"proof", "code"}
NUMBER = re.compile(r"[-+]?\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?")
OPTION = re.compile(r"\(?([a-h])\)?[.):]?(?:\s+(.+))?")


def gradable(kind, answer):
    """True when the source's key is short enough to mark an answer against."""
    if not answer or not answer.strip() or kind in NEVER_MARKED:
        return False
    return kind in {"mcq", "numeric"} or len(answer.split()) <= SHORT_KEY_WORDS


def grade(kind, choices, answer, response):
    """True or False against the source's key; None when only self-check is possible."""
    if not gradable(kind, answer):
        return None
    if kind == "mcq":
        key = _option(choices, answer)
        if key is not None:
            return _option(choices, response) == key
    elif kind == "numeric":
        key = _number(answer)
        if key is not None:
            return _number(response) == key
    return _text(response) == _text(answer)


def _text(value):
    # NFC: Vietnamese keyboards may send decomposed accents.
    value = unicodedata.normalize("NFC", collapse(ANSWER.sub("", value, count=1)))
    return value.casefold().strip(" .,;:!?\"'()")


def _option(choices, value):
    """Index of the option ``value`` names, by its letter or its wording."""
    texts = [_text(c) for c in choices]
    value = _text(value)
    if value in texts:
        return texts.index(value)
    match = OPTION.fullmatch(value)
    if not match:
        return None
    index = ord(match.group(1)) - ord("a")
    wording = match.group(2)
    if index >= len(choices) or (wording and _text(wording) != texts[index]):
        return None  # "B. Manual" when B is not Manual names no single option
    return index


def _number(value):
    """The one number an answer gives, read after its last "=" ("4 x 5 = 20").

    shortcut: a comma is read as a decimal point (Vietnamese "1,2"), so "1,500"
    is 1.5; ask for a thousands separator rule if keys ever reach four digits.
    """
    tokens = NUMBER.findall(ANSWER.sub("", value, count=1).rsplit("=", 1)[-1])
    if len(tokens) != 1:
        return None  # none, or a hedge such as "20 or 30"
    return Fraction(re.sub(r"\s+", "", tokens[0]).replace(",", "."))
