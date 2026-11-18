"""Parity and batching tests for syllabus concept extraction and save fastpaths."""

from __future__ import annotations

from sqlalchemy import event, text

from app.concepts import from_pages, syllabus_concepts
from app.concepts.from_pages import _prompt, save_concepts
from app.concepts.syllabus_concepts import (
    _grounded,
    _grounded_from_spans,
    _prepare_page_spans,
    _words,
    extract_course_concepts,
    merge_similar_concepts,
)


def test_grounded_from_spans_matches_wrapped_and_direct_lines():
    page = (
        "Week 1 Syllabus Overview\n"
        "Breadth-First Search and\n"
        "Shortest Paths in Unweighted Graphs\n"
        "Dynamic Programming on DAGs"
    )
    spans = _prepare_page_spans(page)
    for title in [
        "Breadth-First Search",
        "Shortest Paths",
        "Search and Shortest Paths",
        "Dynamic Programming",
        "Missing Topic",
        "",
    ]:
        expected = _grounded(title, page)
        assert _grounded_from_spans(_words(title), spans) == expected


def test_extract_course_concepts_prepares_each_page_once(monkeypatch):
    prep_calls = 0
    orig_prepare = syllabus_concepts._prepare_page_spans

    def counted_prepare(page_text: str):
        nonlocal prep_calls
        prep_calls += 1
        return orig_prepare(page_text)

    monkeypatch.setattr(syllabus_concepts, "_prepare_page_spans", counted_prepare)
    topics = [f"Topic {i}" for i in range(15)]
    pages = ["\n".join(topics)]
    parsed = {
        "weeks": [{"week": 1, "source_page": 1, "topics": topics}],
        "outcomes": [
            {"code": "CLO1", "source_page": 1, "text": f"Understand ({', '.join(topics)})"},
        ],
    }

    concepts = extract_course_concepts(parsed, pages)

    assert len(concepts) == 15
    assert prep_calls == 1
    assert all(c["clo_codes"] == ["CLO1"] for c in concepts)


def test_merge_similar_concepts_skips_dot_product_when_words_disjoint():
    calls = 0

    class CountingNum(float):
        def __mul__(self, other):
            nonlocal calls
            calls += 1
            return super().__mul__(other)

    class StubEncoder:
        def prepare(self, titles):
            return None

        def encode(self, title):
            if "Breadth" in title or "BFS" in title:
                return [CountingNum(1.0), CountingNum(0.0)]
            return [CountingNum(0.0), CountingNum(1.0)]

    concepts = [
        {"title": "Breadth-First Search (BFS)", "week": 1, "source_pages": [1], "clo_codes": []},
        {"title": "BFS", "week": 2, "source_pages": [2], "clo_codes": ["CLO1"]},
        {"title": "Hash Tables", "week": 3, "source_pages": [3], "clo_codes": []},
        {"title": "Sorting Algorithms", "week": 4, "source_pages": [4], "clo_codes": []},
    ]
    merged = merge_similar_concepts(concepts, encoder=StubEncoder())

    assert [c["title"] for c in merged] == [
        "Breadth-First Search (BFS)",
        "Hash Tables",
        "Sorting Algorithms",
    ]
    assert merged[0]["aliases"] == ["BFS"]
    assert calls == 2  # only (BFS vs Breadth-First Search) shared a word and multiplied vectors


def test_save_concepts_batches_updates_and_inserts_and_caches_prompts(app, client, headers):
    names = [
        "arrays", "linked-lists", "stacks", "queues", "heaps", "hashing",
        "binary-trees", "avl-rotations", "tries", "graphs", "dijkstra", "kruskal",
        "topological-sort", "dynamic-programming", "greedy-choice", "backtracking",
        "union-find", "segment-trees", "suffix-arrays", "flow-networks",
    ]
    course_resp = client.post(
        "/api/v1/courses",
        headers=headers,
        json={"title": "AI Perf Course", "level": "university"},
    )
    assert course_resp.status_code == 201
    course_id = course_resp.json()["id"]

    initial = [
        {
            "slug": slug,
            "title": slug.replace("-", " ").title(),
            "summary": f"Summary {slug}",
            "bloom_level": "understand",
            "source_pages": [i + 1],
        }
        for i, slug in enumerate(names[:12])
    ]
    with app.state.database.sessions() as db:
        saved = save_concepts(db, course_id, initial, file_name="deck1.pdf")
        db.execute(
            text("UPDATE concepts SET confirmed = 1 WHERE course_id = :c AND slug = 'arrays'"),
            {"c": course_id},
        )
        db.commit()
    assert len(saved) == 12

    updated = [
        {
            "slug": slug,
            "title": f"Revised {slug.replace('-', ' ').title()}",
            "summary": f"Revised Summary {slug}",
            "bloom_level": "apply",
            "source_pages": [i + 1, i + 20],
        }
        for i, slug in enumerate(names)
    ]

    statements: list[str] = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if "FROM concepts" in statement or "INTO concepts" in statement or "UPDATE concepts" in statement:
            statements.append(statement.strip().split()[0].upper())

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", listener)
    try:
        with app.state.database.sessions() as db:
            result = save_concepts(db, course_id, updated, file_name="deck2.pdf")
            db.commit()
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert len(result) == 20
    assert statements == ["SELECT", "UPDATE", "INSERT"]
    by_slug = {c["slug"]: c for c in result}
    assert by_slug["arrays"]["title"] == "Arrays"  # confirmed keeps original wording
    assert by_slug["stacks"]["title"] == "Revised Stacks"


def test_prompt_reads_file_once_per_path(tmp_path, monkeypatch):
    from_pages._read_prompt_file.cache_clear()
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    prompt_file = prompt_dir / "sample.txt"
    prompt_file.write_text("hello prompt", encoding="utf-8")
    monkeypatch.setattr(from_pages, "PROMPTS", prompt_dir)

    assert _prompt("sample") == "hello prompt"
    info_before = from_pages._read_prompt_file.cache_info()
    assert _prompt("sample") == "hello prompt"
    info_after = from_pages._read_prompt_file.cache_info()
    assert info_after.hits == info_before.hits + 1
