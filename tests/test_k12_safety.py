"""K-12 safety test suite (Issue #164, spec 11.4).

Verifies:
1. 0/50 K-12 accounts can access girlfriend mode.
2. Parental consent is strictly required for minors under 18 upon registration.
3. Data minimization: only birth year is stored, no exact birth date.
4. Self-harm / crisis detection: safe empathetic reply with Vietnam crisis hotlines,
   safety flag set, and raw sensitive content never persisted in chat history.
5. Age-based content filtering for K-12 learners.
6. Complete data export (GET /me/export).
7. Hard account deletion (DELETE /me) with confirmation and cascading cleanup.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.companion import companion_mode, girlfriend_mode_allowed
from app.safety import (
    HOTLINES,
    SAFE_REDACTION_MESSAGE,
    build_crisis_reply,
    is_crisis_message,
    redact_crisis_content,
)
from app.vetting.filters import Learner, content_failure
from assistant.backend.models import (
    AuthSession,
    ChatMessage,
    Course,
    Roadmap,
    RoadmapNode,
    ScheduleEntry,
    Task,
    User,
)


@pytest.fixture
def client(app):
    with TestClient(app) as instance:
        yield instance


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_k12_girlfriend_mode_blocked_50_cases(client, app):
    """Criterion 1: 0/50 K-12 accounts can access girlfriend mode."""
    today = date(2026, 11, 12)
    allowed_count = 0

    # 50 varied K-12 configurations across birth years, verification statuses, and personas
    for i in range(50):
        birth_year = 2000 + (i % 22)  # 2000 to 2021
        adult_verified = 1 if i % 2 == 0 else 0
        user = SimpleNamespace(
            account_level="k12",
            birth_year=birth_year,
            adult_verified=adult_verified,
            companion_mode="girlfriend",
        )

        # 1. girlfriend_mode_allowed must always be False
        if girlfriend_mode_allowed(user, today):
            allowed_count += 1

        # 2. companion_mode must fall back to buddy (never girlfriend)
        effective_mode = companion_mode(user, today)
        assert effective_mode == "buddy", f"Failed on case {i}: {effective_mode}"

    assert allowed_count == 0, f"Expected 0 allowed, got {allowed_count}"

    # Also verify via API PATCH /me for a registered K-12 user
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "k12_student_girlfriend_block@example.com",
            "name": "K12 Student",
            "password": "Password123",
            "birth_year": 2010,
            "account_level": "k12",
            "parental_consent": True,
        },
    )
    assert reg_resp.status_code == 201, reg_resp.text
    token = reg_resp.json()["access_token"]

    patch_resp = client.patch(
        "/api/v1/me",
        headers=_auth(token),
        json={"companion_mode": "girlfriend"},
    )
    assert patch_resp.status_code == 403
    assert "verified adult account" in patch_resp.text


def test_parental_consent_required_for_minors(client, app, clock):
    """Criterion 2: Under-18 learners require parental consent; adults do not."""
    # Under-18 year relative to the test clock (2030): 2015 is age 15 (< 18).
    minor_year = clock[0].year - 15
    adult_year = clock[0].year - 25

    # 1. Minor (<18) without consent -> 422
    resp_minor_no_consent = client.post(
        "/api/v1/auth/register",
        json={
            "email": "minor_no_consent@example.com",
            "name": "Minor Learner",
            "password": "Password123",
            "birth_year": minor_year,
            "account_level": "k12",
            "parental_consent": False,
        },
    )
    assert resp_minor_no_consent.status_code == 422
    assert "Parental consent is required" in resp_minor_no_consent.text

    # 2. Minor (<18) with consent -> 201 and consent timestamp recorded
    resp_minor_consent = client.post(
        "/api/v1/auth/register",
        json={
            "email": "minor_with_consent@example.com",
            "name": "Minor Consented",
            "password": "Password123",
            "birth_year": minor_year,
            "account_level": "k12",
            "parental_consent": True,
        },
    )
    assert resp_minor_consent.status_code == 201
    user_data = resp_minor_consent.json()["user"]
    assert user_data["parental_consent"] is True
    assert user_data["parental_consent_at"] is not None

    with app.state.database.sessions() as db:
        user_row = db.get(User, user_data["id"])
        assert user_row.parental_consent == 1
        assert user_row.parental_consent_at is not None

    # 3. Adult (>=18) without parental consent -> succeeds
    resp_adult = client.post(
        "/api/v1/auth/register",
        json={
            "email": "adult_user@example.com",
            "name": "Adult Learner",
            "password": "Password123",
            "birth_year": adult_year,
            "account_level": "university",
            "parental_consent": False,
        },
    )
    assert resp_adult.status_code == 201
    adult_data = resp_adult.json()["user"]
    assert adult_data["parental_consent"] is False


def test_data_minimization_only_stores_birth_year(client):
    """Data minimization: only birth_year is collected/stored, not full DOB."""
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "minimization@example.com",
            "name": "Minimization Test",
            "password": "Password123",
            "birth_year": 2004,
            "account_level": "university",
        },
    )
    assert resp.status_code == 201
    user = resp.json()["user"]
    assert user["birth_year"] == 2004
    assert "birth_date" not in user
    assert "dob" not in user


def test_self_harm_detection_and_crisis_response(client, app, clock):
    """Criterion 3: Crisis detection, empathetic response with VN hotlines, sensitive text redacted."""
    # Register a learner
    minor_year = clock[0].year - 16
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "crisis_test@example.com",
            "name": "Crisis Test Learner",
            "password": "Password123",
            "birth_year": minor_year,
            "account_level": "k12",
            "parental_consent": True,
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Send crisis message in Vietnamese
    crisis_input = "Mình buồn quá, muốn tự tử và kết thúc tất cả"
    chat_resp = client.post(
        "/api/v1/ai/chat",
        headers=_auth(token),
        json={"message": crisis_input, "mood": "stressed"},
    )
    assert chat_resp.status_code == 200, chat_resp.text
    chat_out = chat_resp.json()

    # 1. Reply contains Vietnam hotlines
    reply = chat_out["reply"]
    assert "111" in reply
    assert "096 306 1414" in reply
    assert "115" in reply
    assert chat_out["safety_flag"] is True
    assert chat_out["fallback_reason"] == "crisis_intervention"

    # 2. Check stored chat history in DB: raw message is REDACTED, safety_flag is 1
    with app.state.database.sessions() as db:
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at)
            .all()
        )
        assert len(messages) == 2
        user_msg, assistant_msg = messages[0], messages[1]

        # Raw suicidal text must NEVER be stored
        assert crisis_input not in user_msg.content
        assert user_msg.content == SAFE_REDACTION_MESSAGE
        assert user_msg.safety_flag == 1

        assert assistant_msg.safety_flag == 1
        assert "111" in assistant_msg.content

    # Advance clock to ensure distinct created_at ordering
    from datetime import timedelta

    clock[0] += timedelta(seconds=10)

    # 3. Regular non-crisis message passes through and is stored normally
    normal_input = "Làm sao để học tốt môn Đại số?"
    normal_resp = client.post(
        "/api/v1/ai/chat",
        headers=_auth(token),
        json={"message": normal_input, "mood": "neutral"},
    )
    assert normal_resp.status_code == 200
    normal_out = normal_resp.json()
    assert normal_out["safety_flag"] is False

    with app.state.database.sessions() as db:
        latest = (
            db.query(ChatMessage)
            .filter(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .first()
        )
        assert latest.safety_flag == 0


def test_self_harm_detector_and_hotlines():
    """Unit test for safety detection logic."""
    assert is_crisis_message("muốn tự tử")
    assert is_crisis_message("toi muon chet")
    assert is_crisis_message("rạch tay tự hại")
    assert is_crisis_message("I want to kill myself")
    assert is_crisis_message("slit my wrist")

    assert not is_crisis_message("Cho tôi hỏi bài tập số 5")
    assert not is_crisis_message("Hôm nay trời đẹp quá")

    reply_vi = build_crisis_reply("vi")
    reply_en = build_crisis_reply("en")

    assert "111" in reply_vi and "096 306 1414" in reply_vi and "115" in reply_vi
    assert "111" in reply_en and "096 306 1414" in reply_en and "115" in reply_en

    assert redact_crisis_content("muốn tự tử") == SAFE_REDACTION_MESSAGE
    assert redact_crisis_content("bình thường") == "bình thường"
    assert len(HOTLINES) == 3


def test_age_based_source_filtering():
    """Criterion 4: K-12 learner vetting filters out adult content."""
    doc_adult = SimpleNamespace(text="Sample content", lang="vi", adult=True)
    doc_safe = SimpleNamespace(text="Sample content", lang="vi", adult=False)

    k12_learner = Learner(langs=("vi", "en"), k12=True)
    univ_learner = Learner(langs=("vi", "en"), k12=False)

    # K-12 blocks adult content
    assert content_failure(doc_adult, k12_learner) == "age"
    assert content_failure(doc_safe, k12_learner) is None

    # University learner does not fail on adult flag
    assert content_failure(doc_adult, univ_learner) is None
    assert content_failure(doc_safe, univ_learner) is None


def test_export_and_delete_account_lifecycle(client, app):
    """Criterion 5: GET /me/export and DELETE /me cascade cleanup."""
    # 1. Register a user and seed user data
    reg = client.post(
        "/api/v1/auth/register",
        json={
            "email": "lifecycle_user@example.com",
            "name": "Lifecycle Learner",
            "password": "Password123",
            "birth_year": 2004,
            "account_level": "university",
        },
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Seed courses, roadmaps, tasks, chat messages
    with app.state.database.sessions() as db:
        course = Course(
            id="course-test-1", owner_id=user_id, title="Test Course", level="k12"
        )
        db.add(course)
        db.flush()

        roadmap = Roadmap(
            id="roadmap-test-1", course_id=course.id, user_id=user_id, title="Roadmap 1"
        )
        db.add(roadmap)
        db.flush()

        node = RoadmapNode(
            id="node-test-1",
            roadmap_id=roadmap.id,
            title="Node 1",
            type="topic",
            week=1,
            duration_minutes=45,
        )
        db.add(node)

        task = Task(
            id="task-test-1",
            owner_id=user_id,
            assignee_id=user_id,
            title="Study Node 1",
            roadmap_node_id=node.id,
            duration_minutes=45,
            status="pending",
            due_at=datetime.now(UTC),
        )
        db.add(task)
        db.flush()

        now_utc = datetime.now(UTC)
        entry = ScheduleEntry(
            id="entry-test-1",
            user_id=user_id,
            task_id=task.id,
            starts_at=now_utc,
            ends_at=now_utc + timedelta(minutes=45),
            status="planned",
        )
        db.add(entry)

        chat = ChatMessage(
            id="chat-test-1",
            user_id=user_id,
            role="user",
            content="Hello companion",
            created_at=datetime.now(UTC),
            safety_flag=0,
        )
        db.add(chat)
        db.commit()

    # 2. Test GET /me/export
    export_resp = client.get("/api/v1/me/export", headers=_auth(token))
    assert export_resp.status_code == 200
    export_data = export_resp.json()

    assert export_data["user"]["id"] == user_id
    assert export_data["user"]["email"] == "lifecycle_user@example.com"
    assert len(export_data["courses"]) == 1
    assert export_data["courses"][0]["id"] == "course-test-1"
    assert len(export_data["roadmaps"]) == 1
    assert export_data["roadmaps"][0]["nodes"][0]["id"] == "node-test-1"
    assert len(export_data["tasks"]) == 1
    assert len(export_data["schedule_entries"]) == 1
    assert len(export_data["chat_messages"]) == 1

    # 3. Test DELETE /me without confirmation -> 400
    del_no_conf = client.delete("/api/v1/me", headers=_auth(token))
    assert del_no_conf.status_code == 400
    assert "Confirmation required" in del_no_conf.text

    # 4. Test DELETE /me with confirmation -> 204
    del_conf = client.delete("/api/v1/me?confirm=true", headers=_auth(token))
    assert del_conf.status_code == 204

    # 5. Verify token is invalidated and user cannot log in
    assert client.get("/api/v1/me", headers=_auth(token)).status_code == 401
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "lifecycle_user@example.com", "password": "Password123"},
    )
    assert login_resp.status_code == 401

    # 6. Verify full cascade cleanup in the database
    with app.state.database.sessions() as db:
        assert db.get(User, user_id) is None
        assert db.query(AuthSession).filter(AuthSession.user_id == user_id).count() == 0
        assert db.query(Course).filter(Course.owner_id == user_id).count() == 0
        assert db.query(Roadmap).filter(Roadmap.user_id == user_id).count() == 0
        assert db.query(Task).filter(Task.owner_id == user_id).count() == 0
        assert (
            db.query(ScheduleEntry).filter(ScheduleEntry.user_id == user_id).count()
            == 0
        )
        assert db.query(ChatMessage).filter(ChatMessage.user_id == user_id).count() == 0
