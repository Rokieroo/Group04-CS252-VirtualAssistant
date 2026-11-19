"""save_items batches its queries; BM25 reuses page tokens without changing scores."""

from __future__ import annotations

from sqlalchemy import event, text

from app.catalog import exercises as catalog_exercises
from app.catalog.exercises import extract_numbered
from app.items.find import save_items
from app.retrieval.bm25 import Bm25Index, _page_tokens


def test_save_items_batches_queries_and_calls_store_private_once_per_source(
    app, client, headers, monkeypatch
):
    course_resp = client.post(
        "/api/v1/courses", headers=headers, json={"title": "Course A"}
    )
    other_resp = client.post(
        "/api/v1/courses", headers=headers, json={"title": "Course B"}
    )
    assert course_resp.status_code == 201 and other_resp.status_code == 201
    course_id = course_resp.json()["id"]
    other_course_id = other_resp.json()["id"]

    page1 = (
        "Exercise 1: Compute the shortest path.\n"
        "A. BFS\n"
        "B. DFS\n"
        "Answer: A. BFS\n"
        "Exercise 2: State the recurrence.\n"
    )
    page2 = "Exercise 3: Prove loop invariant.\nExercise 4: Compare time complexity.\n"
    with app.state.database.sessions() as db:
        db.execute(
            text(
                "INSERT INTO sources (id,course_id,file_name,page,text) "
                "VALUES ('s1',:c,'w1.txt',1,:t1), ('s2',:c,'w1.txt',2,:t2), "
                "('s-other',:oc,'w2.txt',1,:t1)"
            ),
            {"c": course_id, "oc": other_course_id, "t1": page1, "t2": page2},
        )
        db.execute(
            text(
                "INSERT INTO concepts (id,course_id,slug,title,source_pages) "
                "VALUES ('c-fast',:c,'bfs','Breadth-First Search','[1,2]')"
            ),
            {"c": course_id},
        )
        db.commit()

    store_calls = 0
    orig_store_private = catalog_exercises.store_private

    def counted_store(db, source, owner):
        nonlocal store_calls
        store_calls += 1
        return orig_store_private(db, source, owner)

    monkeypatch.setattr(catalog_exercises, "store_private", counted_store)

    items = [
        *[{**item, "source_id": "s1"} for item in extract_numbered(page1)],
        *[{**item, "source_id": "s2"} for item in extract_numbered(page2)],
        # Intra-batch duplicate and cross-course tampered source must both be ignored.
        {**extract_numbered(page1)[0], "source_id": "s1"},
        {**extract_numbered(page1)[0], "source_id": "s-other"},
    ]

    statements: list[str] = []

    def listener(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if "FROM sources" in statement or "INTO items" in statement:
            statements.append(statement)

    engine = app.state.database.engine
    event.listen(engine, "before_cursor_execute", listener)
    try:
        with app.state.database.sessions() as db:
            saved = save_items(db, "c-fast", items)
            db.commit()
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    assert len(saved) == 4
    assert store_calls == 2
    assert len([s for s in statements if "FROM sources" in s]) == 1
    assert len([s for s in statements if "INTO items" in s]) == 1

    with app.state.database.sessions() as db:
        assert save_items(db, "c-fast", items) == []  # already saved


def test_cached_page_tokens_score_like_fresh_ones():
    docs = ["cây nhị phân tìm kiếm", "bảng băm và xung đột", "đồ thị " * 3000]
    _page_tokens.cache_clear()
    cold = Bm25Index(docs).scores("cây nhị phân")
    warm = Bm25Index(docs).scores("cây nhị phân")

    assert cold == warm and cold[0] > 0
    assert _page_tokens.cache_info().currsize == 2  # the 18k-char page is not kept
