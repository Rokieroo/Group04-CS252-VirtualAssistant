"""What to study today (#158): the pure plan and GET /today for three learner profiles."""

import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.planner.today import (
    MIN_STUDY_MINUTES,
    REVIEW_MINUTES,
    DueReview,
    LearnerDay,
    StudyNode,
    today,
)
from app.roadmap import Edge
from assistant.backend.models import ReviewCard, RoadmapNode

DAY = datetime(2030, 1, 7, tzinfo=UTC)
END = DAY + timedelta(days=1)


def day(nodes, edges=(), reviews=(), free=((DAY, END),)):
    return LearnerDay(DAY, END, list(nodes), list(edges), list(reviews), list(free))


def _random_day(rng: random.Random) -> LearnerDay:
    """A DAG of topics and milestones with random edge kinds, progress and free time."""
    count = rng.randint(1, 20)
    ids = [f"n{i}" for i in range(count)]
    nodes = [
        StudyNode(
            key,
            key,
            rng.choice(["topic", "topic", "milestone"]),
            rng.choice([0, 15, 30, 60, 90]),
            done=rng.random() < 0.3,
            due_at=rng.choice([None, DAY + timedelta(days=rng.randint(-3, 20))]),
            release_at=rng.choice([None, DAY + timedelta(days=rng.randint(-7, 7))]),
            planned_today=rng.random() < 0.2,
        )
        for key in ids
    ]
    edges = [
        Edge(ids[a], ids[b], rng.choice(["strict", "covers", "soft"]))
        for a in range(count)
        for b in range(a + 1, count)
        if rng.random() < 0.15
    ]
    reviews = [
        DueReview(f"card{i}", DAY + timedelta(hours=rng.randint(-72, 23)), rng.choice(ids + [None]))
        for i in range(rng.randint(0, 12))
    ]
    start = DAY + timedelta(minutes=rng.randint(0, 1200))
    free = [(start, start + timedelta(minutes=rng.randint(0, 300)))]
    return LearnerDay(DAY, END, nodes, edges, reviews, free)


def _ancestors(learner: LearnerDay, key: str) -> set[str]:
    parents: dict[str, list[str]] = {}
    for edge in learner.edges:
        if edge.kind in {"strict", "covers"}:
            parents.setdefault(edge.child, []).append(edge.parent)
    seen, stack = set(), [key]
    while stack:
        for parent in parents.get(stack.pop(), []):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def test_never_suggests_a_node_with_an_unfinished_strict_prerequisite():
    rng = random.Random(158)
    for _ in range(500):
        learner = _random_day(rng)
        done = {node.id for node in learner.nodes if node.done}
        plan = today(learner, DAY + timedelta(minutes=rng.randint(0, 1440)))
        studied = [item.node_id for item in plan.items + plan.deferred if item.kind == "study"]
        for node_id in studied:
            assert node_id not in done
            assert _ancestors(learner, node_id) <= done, node_id
        assert len(studied) == len(set(studied))


def test_total_never_exceeds_the_free_time_left_today():
    rng = random.Random(1158)
    for _ in range(500):
        learner = _random_day(rng)
        now = DAY + timedelta(minutes=rng.randint(0, 1440))
        plan = today(learner, now)
        free = sum(
            max(0, int((min(end, END) - max(start, now)).total_seconds() // 60))
            for start, end in learner.free
        )
        assert plan.free_minutes == free
        assert plan.total_minutes <= plan.free_minutes
        assert all(item.minutes > 0 for item in plan.items)


def test_a_checkpoint_pulls_its_path_forward_with_a_real_reason():
    next_week = DAY + timedelta(days=7)
    learner = day(
        [
            StudyNode("a", "Mảng", "topic", 60, done=True),
            StudyNode("b", "Danh sách liên kết", "topic", 60, release_at=next_week),
            StudyNode("c", "Cây", "topic", 60, release_at=next_week),
            StudyNode("m", "Giữa kỳ", "milestone", 30, due_at=DAY + timedelta(days=6, hours=9)),
        ],
        [Edge("a", "b"), Edge("b", "c"), *(Edge(t, "m", "covers") for t in "abc")],
    )
    plan = today(learner, DAY)
    # "b" opens next week but the midterm needs it; "c" still waits for "b".
    assert [(item.node_id, item.reason) for item in plan.items] == [
        ("b", "Giữa kỳ còn 6 ngày, còn 2 chặng phải học trước")
    ]
    assert plan.deferred == []


def test_a_milestone_is_reviewed_once_everything_it_covers_is_done():
    learner = day(
        [
            StudyNode("a", "Mảng", "topic", 60, done=True),
            StudyNode("m", "Giữa kỳ", "milestone", 30, due_at=DAY + timedelta(hours=20)),
        ],
        [Edge("a", "m", "covers")],
    )
    (item,) = today(learner, DAY).items
    assert item.node_id == "m"
    assert item.reason.startswith("Giữa kỳ hôm nay: các chặng cần thiết đã xong")


def test_reviews_come_first_and_the_rest_is_packed_or_deferred():
    learner = day(
        [
            StudyNode("a", "Mảng", "topic", 120, due_at=DAY + timedelta(days=2)),
            StudyNode("b", "Đồ thị", "topic", 60, due_at=DAY + timedelta(days=5)),
        ],
        reviews=[DueReview(f"c{i}", DAY - timedelta(days=2), "a") for i in range(5)],
        free=[(DAY + timedelta(hours=19), DAY + timedelta(hours=20))],
    )
    plan = today(learner, DAY)
    review, study = plan.items
    assert (review.kind, review.title, review.minutes) == ("review", "Ôn tập: Mảng", 5 * REVIEW_MINUTES)
    assert review.reason == "5 thẻ ôn tập đến hạn theo FSRS, thẻ cũ nhất quá hạn 2 ngày"
    assert (study.node_id, study.minutes) == ("a", 50)
    assert study.reason == "Hạn còn 2 ngày · hôm nay học 50/120 phút"
    assert [item.node_id for item in plan.deferred] == ["b"]
    assert plan.total_minutes == plan.free_minutes == 60


def test_only_the_reviews_that_fit_are_kept():
    learner = day(
        [],
        reviews=[DueReview(f"c{i}", DAY, None) for i in range(10)],
        free=[(DAY, DAY + timedelta(minutes=7))],
    )
    (item,) = today(learner, DAY).items
    assert (item.title, item.minutes, item.item_ids) == ("Ôn tập thẻ đến hạn", 6, ("c0", "c1", "c2"))
    assert item.reason.endswith("hôm nay đủ thời gian cho 3/10 thẻ")


def test_a_sliver_of_time_is_not_worth_starting_a_node():
    learner = day(
        [StudyNode("a", "Mảng", "topic", 60)],
        free=[(DAY, DAY + timedelta(minutes=MIN_STUDY_MINUTES - 1))],
    )
    plan = today(learner, DAY)
    assert plan.items == [] and [item.node_id for item in plan.deferred] == ["a"]


def test_planned_sessions_lead_and_a_week_not_started_waits():
    learner = day(
        [
            StudyNode("later", "Tuần sau", "topic", 30, release_at=END + timedelta(days=1)),
            StudyNode("open", "Đang mở", "topic", 30, due_at=DAY + timedelta(days=1)),
            StudyNode("planned", "Đã xếp", "topic", 30, planned_today=True),
        ]
    )
    plan = today(learner, DAY)
    assert [item.node_id for item in plan.items] == ["planned", "open"]
    assert plan.items[0].reason == "Lịch học đã xếp chặng này vào hôm nay"
    assert plan.items[1].reason == "Hạn còn 1 ngày"


def test_nodes_on_a_prerequisite_cycle_are_never_suggested():
    learner = day(
        [StudyNode("a", "A", "topic", 30), StudyNode("b", "B", "topic", 30)],
        [Edge("a", "b"), Edge("b", "a")],
    )
    assert today(learner, DAY).items == []


def test_time_already_past_today_does_not_count():
    learner = day([StudyNode("a", "A", "topic", 60)], free=[(DAY, DAY + timedelta(hours=2))])
    plan = today(learner, DAY + timedelta(minutes=90))
    assert plan.free_minutes == 30 and plan.items[0].minutes == 30


# --- GET /today, one learner per profile ----------------------------------------------

LOCAL = timedelta(hours=7)  # every learner below keeps the default Asia/Ho_Chi_Minh


def _learner(client, name, email, **extra):
    response = client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "correct-horse-123",
              "birth_year": 2004, **extra},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def _roadmap(client, headers, nodes, level="university"):
    course = client.post(
        "/api/v1/courses", headers=headers, json={"title": "Course", "level": level}
    ).json()["id"]
    response = client.post(
        f"/api/v1/courses/{course}/roadmap:generate", headers=headers, json={"nodes": nodes}
    )
    assert response.status_code == 201, response.text
    roadmap = response.json()
    return roadmap["id"], {node["title"]: node["id"] for node in roadmap["nodes"]}


def _strict(client, headers, roadmap_id, parent, child):
    response = client.post(
        f"/api/v1/roadmaps/{roadmap_id}/graph/edges",
        headers=headers,
        json={"parent": parent, "child": child, "kind": "strict"},
    )
    assert response.status_code == 201, response.text


def _local(now, hours):
    """``hours`` after local midnight of ``now``'s local day, as a UTC instant."""
    return (now + LOCAL).replace(hour=0, minute=0) - LOCAL + timedelta(hours=hours)


def _free(client, headers, now, *windows):
    body = [
        {"starts_at": _local(now, a).isoformat(), "ends_at": _local(now, b).isoformat()}
        for a, b in windows
    ]
    response = client.put("/api/v1/availability", headers=headers, json={"windows": body})
    assert response.status_code == 200, response.text


def _today(client, headers):
    response = client.get("/api/v1/today", headers=headers)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["total_minutes"] == sum(item["minutes"] for item in plan["items"])
    assert plan["total_minutes"] <= plan["free_minutes"]
    return plan


def _studied(plan, key="items"):
    return [item["node_id"] for item in plan[key] if item["kind"] == "study"]


def _mark_known(app, node_id):
    with app.state.database.sessions() as db:
        db.get(RoadmapNode, node_id).known = "learner"
        db.commit()


def test_university_student_prepares_for_the_midterm(app, client, clock):
    headers = _learner(client, "Minh", "minh@example.com")
    now = clock[0]
    roadmap_id, ids = _roadmap(client, headers, [
        {"title": "Mảng", "week": 1},
        {"title": "Danh sách liên kết", "week": 1},
        {"title": "Cây", "week": 2},
        {"title": "Giữa kỳ", "type": "milestone", "due_at": (now + timedelta(days=6)).isoformat()},
    ])
    _strict(client, headers, roadmap_id, ids["Mảng"], ids["Danh sách liên kết"])
    _free(client, headers, now, (19, 21))

    plan = _today(client, headers)
    assert plan["day"] == "2030-01-07" and plan["free_minutes"] == 120
    assert _studied(plan) == [ids["Mảng"], ids["Cây"]]
    assert {item["reason"] for item in plan["items"]} == {
        "Giữa kỳ còn 6 ngày, còn 3 chặng phải học trước"
    }
    locked = ids["Danh sách liên kết"]
    assert locked not in _studied(plan) + _studied(plan, "deferred")

    _mark_known(app, ids["Mảng"])
    assert locked in _studied(_today(client, headers))


def test_k12_learner_gets_due_reviews_and_part_of_a_lesson(app, client, clock):
    headers = _learner(client, "An", "an@example.com", birth_year=2014,
                       account_level="k12", parental_consent=True)
    now = clock[0]
    _, ids = _roadmap(client, headers, [
        {"title": "Phân số", "week": 1},
        {"title": "Số thập phân", "week": 2},
        {"title": "Kiểm tra 15 phút", "type": "milestone",
         "due_at": (now + timedelta(days=14)).isoformat()},
    ], level="k12")
    _due_card(app, client, headers, ids["Phân số"], now - timedelta(days=1))
    _free(client, headers, now, (18, 18.75))

    plan = _today(client, headers)
    review, study = plan["items"]
    assert review["kind"] == "review" and review["minutes"] == REVIEW_MINUTES
    assert review["reason"] == "1 thẻ ôn tập đến hạn theo FSRS, thẻ cũ nhất quá hạn 1 ngày"
    assert study["node_id"] == ids["Phân số"] and study["minutes"] == 45 - REVIEW_MINUTES
    assert study["reason"] == (
        f"Kiểm tra 15 phút còn 14 ngày, còn 2 chặng phải học trước"
        f" · hôm nay học {45 - REVIEW_MINUTES}/60 phút"
    )
    assert _studied(plan, "deferred") == [ids["Số thập phân"]]
    assert plan["total_minutes"] == plan["free_minutes"] == 45


def test_self_learner_follows_the_goal_path_around_busy_time(client, clock):
    headers = _learner(client, "Lan", "lan@example.com")
    roadmap_id, ids = _roadmap(client, headers, [
        {"title": "Python cơ bản"}, {"title": "Hàm"}, {"title": "Lớp"},
    ])
    _strict(client, headers, roadmap_id, ids["Python cơ bản"], ids["Hàm"])
    _strict(client, headers, roadmap_id, ids["Hàm"], ids["Lớp"])
    now = clock[0]
    _free(client, headers, now, (8, 10))
    busy = client.post("/api/v1/busy-blocks", headers=headers, json={
        "starts_at": _local(now, 9).isoformat(), "ends_at": _local(now, 9.5).isoformat(),
    })
    assert busy.status_code == 201, busy.text

    plan = _today(client, headers)
    assert plan["free_minutes"] == 90
    assert _studied(plan) == [ids["Python cơ bản"]]
    assert plan["items"][0]["reason"] == "Chặng tiếp theo trong lộ trình"
    assert plan["deferred"] == []  # "Hàm" and "Lớp" are locked, not merely out of time


def test_today_only_reads_the_learners_own_roadmaps(client, clock, headers_a, headers_b):
    _roadmap(client, headers_a, [{"title": "Riêng của Lan"}])
    _free(client, headers_b, clock[0], (19, 20))
    plan = _today(client, headers_b)
    assert plan["items"] == [] and plan["deferred"] == []
    assert plan["free_minutes"] == 60


def _due_card(app, client, headers, node_id, due_at):
    """A review card on ``node_id`` that fell due at ``due_at``."""
    user_id = client.get("/api/v1/me", headers=headers).json()["id"]
    concept_id, source_id, item_id = str(uuid4()), str(uuid4()), str(uuid4())
    with app.state.database.sessions() as db:
        course_id = db.scalar(text(
            "SELECT r.course_id FROM roadmaps r JOIN roadmap_nodes n ON n.roadmap_id = r.id "
            "WHERE n.id = :n"), {"n": node_id})
        db.execute(text("INSERT INTO concepts (id, course_id, slug, title, source_pages) "
                        "VALUES (:id, :c, 'phan-so', 'Phân số', '[1]')"),
                   {"id": concept_id, "c": course_id})
        db.execute(text("INSERT INTO sources (id, course_id, file_name, page, text) "
                        "VALUES (:id, :c, 'toan.pdf', 1, 'Bài 1')"),
                   {"id": source_id, "c": course_id})
        db.execute(text("INSERT INTO items (id, concept_id, source_id, type, prompt, answer, status) "
                        "VALUES (:id, :c, :s, 'short', 'Bài 1', '1/2', 'ready')"),
                   {"id": item_id, "c": concept_id, "s": source_id})
        db.add(ReviewCard(user_id=user_id, item_id=item_id, node_id=node_id, due_at=due_at))
        db.commit()
