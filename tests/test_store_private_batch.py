"""Batch lookup/insert and query-count tests for store_private (#115)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.catalog.exercises import store_private
from assistant.backend.models import Course, User


def _seed_course_and_source(db, page_text: str):
    uid = str(uuid4())
    cid = str(uuid4())
    sid = str(uuid4())
    db.add(
        User(
            id=uid,
            email=f"storepriv-{uid[:6]}@example.com",
            password_hash="test-hash",
            name="Tester",
        )
    )
    db.flush()
    db.add(Course(id=cid, owner_id=uid, title="CS101", language="en", level="university"))
    db.flush()
    db.execute(
        text(
            "INSERT INTO sources (id, course_id, file_name, page, text) "
            "VALUES (:id, :cid, 'hw.txt', 1, :text)"
        ),
        {"id": sid, "cid": cid, "text": page_text},
    )
    db.commit()
    return uid, {"id": sid, "course_id": cid, "page": 1, "text": page_text}


def test_store_private_batches_select_and_insert_and_is_idempotent(app, client):
    """store_private hashes once, batches existing-ID SELECT and INSERT, and skips duplicates on retry."""
    lines = []
    for i in range(1, 13):
        lines.append(
            f"Exercise {i}. Compute value {i} mod 5?\n"
            f"A) {i % 5}\n"
            f"B) {(i + 1) % 5}\n"
            f"Answer: {i % 5}\n"
        )
    page_text = "\n".join(lines)

    with app.state.database.sessions() as db:
        uid, source = _seed_course_and_source(db, page_text)

        # Wrong owner rejected immediately
        with pytest.raises(LookupError):
            store_private(db, source, owner_id="wrong-user")

        executed: list[str] = []

        def _track(conn, cursor, statement, parameters, context, executemany):
            executed.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _track)
        try:
            first = store_private(db, source, owner_id=uid)
            db.commit()
        finally:
            event.remove(engine, "before_cursor_execute", _track)

        assert len(first) == 12
        # 1 owner check + 1 IN lookup + 1 batched executemany INSERT = 3 DBAPI calls
        assert len(executed) == 3

        # Re-running against partially or fully existing IDs inserts zero new rows
        executed.clear()
        event.listen(engine, "before_cursor_execute", _track)
        try:
            second = store_private(db, source, owner_id=uid)
            db.commit()
        finally:
            event.remove(engine, "before_cursor_execute", _track)

        assert [r["id"] for r in second] == [r["id"] for r in first]
        assert len(executed) == 2
        count = db.scalar(
            text("SELECT COUNT(*) FROM exercises WHERE source_id = :sid"),
            {"sid": source["id"]},
        )
        assert count == 12
