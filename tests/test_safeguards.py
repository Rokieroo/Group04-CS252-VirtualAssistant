"""Safeguard CI tests for Zero AI-authored questions and unverified resource isolation (issue #106).

Done when:
1. 'Không câu hỏi do AI soạn': exercises leave the API only with a citation, and the exercise
   benchmark fixture quotes its own source text verbatim;
   no prompt in src/ asks a model to author, compose, or invent questions.
2. 'Nguồn chưa xác minh không bao giờ hiện cho người học': unverified, stale, rejected, and dead links
   never reach learner endpoints or search; nodes with insufficient verified resources report 'insufficient'.
3. 30 red-team answer-leak fixtures are well formed (they run once the hint ladder #163 exists).
4. 15 injection HTML fixtures are neutralized by content and safety filters.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_role_catalog import add_resource, roadmap  # noqa: F401 (fixture)

from app.catalog.exercises import exact, quote_hash
from app.search.catalog import CatalogSearch
from app.vetting.document import readable_pages
from app.vetting.fetch import FetchResult
from assistant.backend.catalog_repository import verified_resources
from assistant.backend.maintenance import _remove_everywhere
from assistant.backend.models import NodeResource, Resource
from assistant.backend.routes_learning import ExerciseCitationOut

ROOT = Path(__file__).resolve().parents[1]
EXERCISES_BENCHMARK = ROOT / "eval" / "exercises.jsonl"
ANSWER_LEAKS_FIXTURE = ROOT / "eval" / "fixtures" / "redteam" / "answer_leaks.jsonl"
INJECTIONS_DIR = ROOT / "eval" / "fixtures" / "redteam" / "injections"

AUTHORING_VERBS = (
    "write", "generate", "create", "compose", "invent", "paraphrase", "rephrase",
    "viết", "tạo", "sinh",
)
QUESTION_NOUNS = ("question", "questions", "exercise", "exercises", "quiz", "mcq")


def _docstrings(tree: ast.AST) -> set[int]:
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
    }


def test_safeguard_no_llm_prompt_asks_a_model_to_author_questions():
    """Safeguard 1A: Static AST scan across src/ ensuring no prompt instructs a model to write test questions."""
    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstrings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstrings
            ):
                words = node.value.casefold().split()
                if any(a in words for a in AUTHORING_VERBS) and any(q in words for q in QUESTION_NOUNS):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], f"Found LLM prompts attempting to author questions: {offenders}"


def test_exercise_benchmark_fixture_is_internally_consistent():
    """The 60 cases quote their own ``source_text`` verbatim and carry the matching quote hash.

    The cases are synthetic grading fixtures: each ``source_text`` was written with the case,
    so this proves the fixture is consistent, not that it comes from real course material.
    """
    assert EXERCISES_BENCHMARK.is_file(), f"Missing {EXERCISES_BENCHMARK}"
    lines = EXERCISES_BENCHMARK.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    assert len(cases) >= 60, f"Expected at least 60 exercises, found {len(cases)}"

    for case in cases:
        cid = case["id"]
        source = case.get("source", {})
        assert source.get("title"), f"{cid} missing source title"
        assert source.get("location"), f"{cid} missing source location"
        source_text = source.get("source_text", "")
        assert source_text, f"{cid} missing source text"

        prompt = case.get("prompt", "")
        choices = case.get("choices") or []
        answer = case.get("answer")

        # Must match verbatim in source text
        assert exact({"prompt": prompt, "choices": choices, "answer": answer}, source_text), (
            f"{cid}: prompt/choices/answer is not verbatim in source text"
        )

        # Must have matching quote hash
        expected_hash = quote_hash(prompt, choices, answer)
        assert case.get("quote_hash") == expected_hash, f"{cid}: quote_hash mismatch"


def test_safeguard_exercise_citation_out_enforces_source_attribution():
    """Safeguard 1C: API schema strictly forbids an exercise without source citation from leaving the API."""
    fields = {"title": "Title", "url": None, "institution": None, "license": "private"}
    with pytest.raises(ValidationError):
        ExerciseCitationOut(source_id=None, resource_id=None, **fields)
    with pytest.raises(ValidationError):
        ExerciseCitationOut(source_id="s1", resource_id="r1", **fields)
    valid = ExerciseCitationOut(source_id="s1", resource_id=None, **fields)
    assert valid.source_id == "s1"


@pytest.mark.parametrize("unverified_status", ["pending", "rejected", "stale"])
def test_safeguard_unverified_resources_never_shown_to_learners(app, client, headers, clock, unverified_status):
    """Safeguard 2A: Resources in pending, rejected, or stale status must never be returned to learners."""
    now = clock[0]
    sessions = app.state.database.sessions
    with sessions() as db:
        res = Resource(
            url=f"https://example.edu/unverified-{unverified_status}",
            canonical_url=f"https://example.edu/unverified-{unverified_status}",
            title="Unverified Resource",
            provider="web",
            lang="en",
            kind="reading",
            format="reading",
            license="CC-BY-4.0",
            verification_status=unverified_status,
        )
        db.add(res)
        db.commit()
        res_id = res.id

        # 1. verified_resources() must never return it
        verified = verified_resources(db, now)
        assert res_id not in {r["id"] for r in verified}

        # 2. CatalogSearch must never return it
        search_res = CatalogSearch(session=db, now=now).search("Unverified Resource", lang="en")
        assert res_id not in {r.id for r in search_res}


def test_safeguard_dead_links_removed_from_learner_views(app, client, clock, roadmap):  # noqa: F811
    """Safeguard 2B: Links that failed consecutive checks are pruned from shown views (0% dead links)."""
    node_id = roadmap["nodes"][0]["id"]
    sessions = app.state.database.sessions
    with sessions() as db:
        res = add_resource(db, clock[0], number=9)
        res.failed_checks = 2
        res.http_status = 404

        # Place on a node
        node_res = NodeResource(node_id=node_id, resource_id=res.id, status="shown")
        db.add(node_res)
        db.commit()

        # Run removal of dead links
        removed = _remove_everywhere(db, res.id)
        db.commit()
        assert removed == 1

        db.refresh(node_res)
        assert node_res.status == "removed"


def test_answer_leak_fixtures_are_well_formed():
    """The 30 answer-leak attacks are ready to run: each targets a graded item and expects refusal.

    Only the fixture format is checked. Nothing in the app hints or grades at a node yet (#163),
    so no attack is sent and no leak rate is measured until that exists.
    """
    assert ANSWER_LEAKS_FIXTURE.is_file(), f"Missing {ANSWER_LEAKS_FIXTURE}"
    lines = ANSWER_LEAKS_FIXTURE.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    assert len(cases) >= 30, f"Expected at least 30 answer leak cases, found {len(cases)}"

    for case in cases:
        assert case["assessment_type"] in ("graded_quiz", "midterm_exam", "final_exam", "graded_assignment")
        assert case["expected"] == "refuse_final_answer"
        assert case["max_hint_level"] == 1


def test_safeguard_injection_html_fixtures_neutralized():
    """Safeguard 4: All 15 injection HTML fixtures must be safely parsed and sanitized without raw script execution."""
    html_files = sorted(INJECTIONS_DIR.glob("*.html"))
    assert len(html_files) >= 15, f"Expected at least 15 injection HTML files, found {len(html_files)}"

    for html_file in html_files:
        raw_bytes = html_file.read_bytes()
        res = FetchResult(
            url="https://example.edu/inj",
            status=200,
            content_type="text/html",
            body=raw_bytes,
        )
        pages = readable_pages(res)
        for page_text in pages:
            assert "<script" not in page_text.lower()
            assert "onerror=" not in page_text.lower()
