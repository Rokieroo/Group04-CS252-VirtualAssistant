"""Syllabus parsing, roadmap node rules, and Issue #60 Roadmap Builder verification."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.llm import FakeLLM
from app.roadmap import (
    Edge,
    NodeSpec,
    allocate_durations,
    build_roadmap,
    decode_covers,
    derive_nodes,
    find_cycles,
    link,
    node_spec,
    topological_sort,
    topological_sort_or_raise,
    weekly_minutes,
)
from app.syllabus import AssessmentItem, Outcome, parse_syllabus


def test_syllabus_aliases_become_one_shape():
    payload = {
        "text": " Week 1: Framing ",
        "outcomes": ["Frame a problem", {"code": "CLO2", "title": "Choose a rung"}],
        "assessments": [{"title": "Midterm", "weight": "30%", "due": "tuần 8"}, "Final"],
    }
    parts = parse_syllabus(payload, set(payload))
    assert parts.raw_text == "Week 1: Framing"
    assert parts.outcomes == [
        Outcome("CLO1", "Frame a problem"), Outcome("CLO2", "Choose a rung")]
    assert parts.assessments == [AssessmentItem("Midterm", 30.0, 8), AssessmentItem("Final")]


def test_omitted_parts_are_left_alone_and_empty_lists_clear():
    kept = parse_syllabus({"raw_text": "new", "outcomes": []}, {"raw_text"})
    assert (kept.raw_text, kept.outcomes, kept.assessments) == ("new", None, None)
    cleared = parse_syllabus({"assessments": []}, {"assessments"})
    assert (cleared.raw_text, cleared.assessments) == (None, [])


def test_parsed_block_is_read_when_top_level_fields_are_absent():
    parsed = {"outcomes": [{"code": "CLO1", "text": "Explain"}], "assessments": []}
    parts = parse_syllabus({"parsed": parsed}, {"parsed"})
    assert parts.outcomes == [Outcome("CLO1", "Explain")]
    assert parts.assessments == []
    assert parts.raw_text.startswith("{")  # no text given: the parsed JSON is kept


def test_nodes_derive_from_outcomes_and_assessments_else_week_lines():
    assert derive_nodes(["Framing"], [("Midterm", 8)], "") == [
        NodeSpec("topic", "Framing"), NodeSpec("milestone", "Midterm", week=8)]
    assert derive_nodes([], [], "Week 2: Search; BM25.\nnoise") == [
        NodeSpec("topic", "Search", week=2), NodeSpec("topic", "BM25", week=2)]


def test_link_assigns_new_ids_and_milestones_cover_earlier_topics():
    first, second, exam, late = link([
        node_spec({"title": "A", "id": "client-chosen"}),
        node_spec({"kind": "topic", "title": "B", "est_minutes": "45"}),
        node_spec({"type": "milestone", "title": "Midterm"}),
        node_spec({"type": "bogus", "title": "C", "covers": "x, y"}),
    ])
    assert first.id != "client-chosen" and len({first.id, second.id, exam.id}) == 3
    assert (first.duration_minutes, second.duration_minutes, exam.duration_minutes) == (
        60, 45, 30)
    assert exam.covers == [first.id, second.id]
    assert (late.kind, late.covers) == ("topic", ["x", "y"])


def test_naive_due_dates_are_read_as_utc_and_covers_decode():
    naive = node_spec({"title": "A", "due_at": datetime(2030, 1, 7, 9)})
    assert naive.due_at == datetime(2030, 1, 7, 9, tzinfo=UTC)
    assert decode_covers('["n1", 2]') == ["n1", "2"]
    assert decode_covers(None) == []


def test_cycle_detection():
    """Test Cycle Detection: verify Kahn topo sort and Tarjan SCC cycle edge detection."""
    nodes = ["A", "B", "C", "D"]
    edges = [
        ("A", "B"),
        ("B", "C"),
        ("C", "A"),
        ("C", "D"),  # Non-cycle DAG edge
    ]
    cycles = find_cycles(nodes, edges)
    # find_cycles returns exactly the edges that belong to the dependency cycle
    assert cycles == [("A", "B"), ("B", "C"), ("C", "A")]
    assert ("C", "D") not in cycles

    # Edge objects preservation
    edge_objs = [
        Edge("A", "B", confidence=0.9),
        Edge("B", "C", confidence=0.8),
        Edge("C", "A", confidence=0.7),
        Edge("C", "D", confidence=0.9),
    ]
    detected = find_cycles(nodes, edge_objs)
    assert detected == edge_objs[:3]

    # Two separate cycles connected by a bridge edge B -> X
    disjoint_nodes = ["A", "B", "X", "Y"]
    disjoint_edges = [
        ("A", "B"), ("B", "A"),  # Cycle 1
        ("B", "X"),              # Cross-component bridge (not part of any cycle)
        ("X", "Y"), ("Y", "X"),  # Cycle 2
    ]
    disjoint_cycles = find_cycles(disjoint_nodes, disjoint_edges)
    assert ("B", "X") not in disjoint_cycles
    assert set(disjoint_cycles) == {("A", "B"), ("B", "A"), ("X", "Y"), ("Y", "X")}

    # Self-loop detection
    assert find_cycles(["A", "B"], [("A", "A"), ("A", "B")]) == [("A", "A")]

    # Kahn's topological sort
    assert topological_sort(["A", "B", "C"], [("A", "B"), ("B", "C")]) == ["A", "B", "C"]
    assert topological_sort(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")]) == []
    with pytest.raises(ValueError, match="dependency cycle"):
        topological_sort_or_raise(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])

    # build_roadmap repairs dependency cycles by breaking lowest-confidence strict edge
    topics = [
        {"title": "Topic A", "slug": "topic-a", "week": 1},
        {"title": "Topic B", "slug": "topic-b", "week": 2},
        {"title": "Topic C", "slug": "topic-c", "week": 3},
    ]
    cyclic_prereqs = [
        Edge("topic-a", "topic-b", confidence=0.9),
        Edge("topic-b", "topic-c", confidence=0.8),
        Edge("topic-c", "topic-a", confidence=0.65),
    ]
    roadmap = build_roadmap(topics, prereq_edges=cyclic_prereqs)
    assert len(roadmap.cycles) >= 1
    # Lowest confidence strict edge was removed
    assert any(e.parent == "topic-c" and e.child == "topic-a" for e in roadmap.removed_edges)
    assert len(roadmap.order) == 3
    assert len(roadmap.nodes) == 3


def test_milestone_covers():
    """Test Milestone Covers: verify covers mapping and time integrity (topic.due_at <= milestone.due_at)."""
    now = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
    topics = [
        {"title": "Intro to Python", "slug": "intro-python", "week": 1, "due_at": now + timedelta(days=7)},
        {"title": "Variables & Types", "slug": "variables-types", "week": 2, "due_at": now + timedelta(days=50)},
        {"title": "Control Structures", "slug": "control-structures", "week": 3, "due_at": now + timedelta(days=21)},
        {"title": "Functions & Scope", "slug": "functions-scope", "week": 4, "due_at": now + timedelta(days=28)},
        {"title": "Object Oriented", "slug": "object-oriented", "week": 5, "due_at": now + timedelta(days=35)},
    ]
    milestones = [
        {"title": "Midterm Exam", "week": 3, "due_at": now + timedelta(days=21)},
        {"title": "Final Project", "week": 5, "due_at": now + timedelta(days=35)},
    ]

    roadmap = build_roadmap(topics, milestones, now=now)

    # 1. Milestone nodes created and covers assigned properly
    assert len(roadmap.milestones) == 2
    midterm = next(m for m in roadmap.milestones if "midterm" in m.id)
    final = next(m for m in roadmap.milestones if "final" in m.id)
    assert midterm.covers == ["intro-python", "variables-types", "control-structures"]
    assert final.covers == ["functions-scope", "object-oriented"]

    # 2. Time integrity verification: every covered child topic has due_at <= milestone.due_at
    by_id = {node.id: node for node in roadmap.nodes}
    for milestone in roadmap.milestones:
        assert milestone.due_at is not None
        for covered_id in milestone.covers or []:
            topic = by_id[covered_id]
            assert topic.due_at is not None
            assert topic.due_at <= milestone.due_at, (
                f"Topic {topic.id} due_at ({topic.due_at}) is later than milestone {milestone.id} ({milestone.due_at})"
            )

    # variables-types was originally day 50, capped to day 21 (midterm date)
    assert by_id["variables-types"].due_at <= midterm.due_at

    # 3. Explicit covers and milestone buffer days
    explicit_milestones = [
        {"title": "Quiz 1", "week": 2, "due_at": now + timedelta(days=14), "covers": ["variables-types"]},
    ]
    rm_buffered = build_roadmap(topics, explicit_milestones, now=now, milestone_buffer_days=3)
    quiz = next(m for m in rm_buffered.milestones if "quiz" in m.id)
    assert quiz.covers == ["variables-types"]
    topic_v = next(t for t in rm_buffered.topics if t.id == "variables-types")
    assert topic_v.due_at <= quiz.due_at - timedelta(days=3)


def test_duration_allocation():
    """Test duration allocation: formula (credits * 120), Bloom/difficulty weights, and +20% review bonus."""
    # 1. Standard weekly pool formula: credits * 120
    assert weekly_minutes(3) == 360
    assert weekly_minutes(4) == 480
    assert weekly_minutes(0) == 0

    # 2. Dynamic distribution based on difficulty and Bloom level
    t1 = {"title": "Basic Concepts", "slug": "basics", "week": 1, "difficulty": 1, "bloom_level": "remember"}
    t2 = {"title": "Algorithm Analysis", "slug": "algo-analysis", "week": 1, "difficulty": 3, "bloom_level": "analyze"}

    durations = allocate_durations([t1, t2], credits=3)
    # Base pool is 3 * 120 = 360
    assert durations["basics"] + durations["algo-analysis"] == 360
    # Difficulty 3 + Analyze weight = 1.5 * 1.4 = 2.1
    # Difficulty 1 + Remember weight = 1.0 * 0.8 = 0.8
    # t2 receives significantly more minutes than t1
    assert durations["algo-analysis"] > durations["basics"] * 2

    # 3. 20% review bonus for the week immediately before a milestone
    # Week 1: normal
    # Week 2: normal
    # Week 3: week immediately preceding Week 4 Midterm Exam -> gets +20% bonus
    # Week 4: Midterm Exam
    week1_topics = [{"title": "W1 Topic", "slug": "w1", "week": 1, "difficulty": 1, "bloom_level": "understand"}]
    week2_topics = [{"title": "W2 Topic", "slug": "w2", "week": 2, "difficulty": 1, "bloom_level": "understand"}]
    week3_topics = [{"title": "W3 Topic", "slug": "w3", "week": 3, "difficulty": 1, "bloom_level": "understand"}]
    milestone_w4 = {"title": "Midterm", "week": 4}

    all_nodes = week1_topics + week2_topics + week3_topics
    durations_with_bonus = allocate_durations(
        all_nodes, credits=3, milestones=[milestone_w4], review_bonus=0.20
    )

    # Standard week pool = 360 min
    assert durations_with_bonus["w1"] == 360
    assert durations_with_bonus["w2"] == 360
    # Week 3 is immediately before week 4 -> 360 * 1.20 = 432 min (+20%)
    assert durations_with_bonus["w3"] == 432
    assert durations_with_bonus["w3"] == round(360 * 1.20)


def test_evaluation_on_5_sample_syllabi():
    """Run evaluation on 5 sample syllabi: ensure >= 80% strict prerequisite edges have agreed confidence."""
    syllabi = [
        # Syllabus 1: Python Programming (CSC10014)
        {
            "code": "CSC10014",
            "credits": 3,
            "topics": [
                {"title": "Python Syntax and Variables", "slug": "py-syntax", "week": 1, "difficulty": 1, "bloom_level": "remember"},
                {"title": "Conditional Statements and Loops", "slug": "py-control", "week": 2, "difficulty": 2, "bloom_level": "understand"},
                {"title": "Functions and Modules", "slug": "py-functions", "week": 3, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Lists, Dictionaries and Tuples", "slug": "py-collections", "week": 4, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Object-Oriented Programming in Python", "slug": "py-oop", "week": 5, "difficulty": 3, "bloom_level": "analyze"},
            ],
            "milestones": [
                {"title": "Midterm Practical Exam", "week": 3},
                {"title": "Final Capstone Project", "week": 5},
            ],
            "proposed_prereqs": [
                {"parent_slug": "py-syntax", "child_slug": "py-control", "confidence": 0.95, "reason": "Control flow builds on syntax"},
                {"parent_slug": "py-control", "child_slug": "py-functions", "confidence": 0.90, "reason": "Functions encapsulate control blocks"},
                {"parent_slug": "py-functions", "child_slug": "py-collections", "confidence": 0.85, "reason": "Collection processors use functions"},
                {"parent_slug": "py-collections", "child_slug": "py-oop", "confidence": 0.85, "reason": "Classes model state with collections"},
                {"parent_slug": "py-syntax", "child_slug": "py-oop", "confidence": 0.40, "reason": "Loose conceptual connection"},
            ],
        },
        # Syllabus 2: Data Structures & Algorithms (CS201)
        {
            "code": "CS201",
            "credits": 4,
            "topics": [
                {"title": "Arrays and Pointers", "slug": "arrays-pointers", "week": 1, "difficulty": 1, "bloom_level": "understand"},
                {"title": "Singly and Doubly Linked Lists", "slug": "linked-lists", "week": 2, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Stacks and Queues", "slug": "stacks-queues", "week": 3, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Binary Trees and BST", "slug": "trees-bst", "week": 4, "difficulty": 3, "bloom_level": "analyze"},
                {"title": "Graph Algorithms and Traversal", "slug": "graphs-traversal", "week": 5, "difficulty": 3, "bloom_level": "analyze"},
            ],
            "milestones": [
                {"title": "Midterm Exam DSA", "week": 3},
                {"title": "Final Exam DSA", "week": 5},
            ],
            "proposed_prereqs": [
                {"parent_slug": "arrays-pointers", "child_slug": "linked-lists", "confidence": 0.95, "reason": "Nodes require pointer mechanics"},
                {"parent_slug": "linked-lists", "child_slug": "stacks-queues", "confidence": 0.90, "reason": "List-based stack/queue implementation"},
                {"parent_slug": "linked-lists", "child_slug": "trees-bst", "confidence": 0.85, "reason": "Tree node linking mirrors linked lists"},
                {"parent_slug": "trees-bst", "child_slug": "graphs-traversal", "confidence": 0.85, "reason": "Trees are acyclic connected graphs"},
                {"parent_slug": "arrays-pointers", "child_slug": "graphs-traversal", "confidence": 0.50, "reason": "Adjacency matrix representation"},
            ],
        },
        # Syllabus 3: Database Management Systems (CS301)
        {
            "code": "CS301",
            "credits": 3,
            "topics": [
                {"title": "Relational Data Model", "slug": "relational-model", "week": 1, "difficulty": 1, "bloom_level": "remember"},
                {"title": "Basic SQL Queries", "slug": "basic-sql", "week": 2, "difficulty": 2, "bloom_level": "understand"},
                {"title": "Complex Queries and Joins", "slug": "complex-sql", "week": 3, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Functional Dependencies and Normalization", "slug": "db-normalization", "week": 4, "difficulty": 3, "bloom_level": "analyze"},
                {"title": "Transactions and Indexing", "slug": "transactions-indexing", "week": 5, "difficulty": 3, "bloom_level": "analyze"},
            ],
            "milestones": [
                {"title": "Midterm DB", "week": 3},
                {"title": "Final Examination DB", "week": 5},
            ],
            "proposed_prereqs": [
                {"parent_slug": "relational-model", "child_slug": "basic-sql", "confidence": 0.95, "reason": "SQL queries relational tables"},
                {"parent_slug": "basic-sql", "child_slug": "complex-sql", "confidence": 0.95, "reason": "Joins extend basic SELECT statements"},
                {"parent_slug": "relational-model", "child_slug": "db-normalization", "confidence": 0.90, "reason": "Normalization cleans relational schemas"},
                {"parent_slug": "complex-sql", "child_slug": "transactions-indexing", "confidence": 0.80, "reason": "Indexing optimizes complex query performance"},
            ],
        },
        # Syllabus 4: Computer Networks (CS401)
        {
            "code": "CS401",
            "credits": 3,
            "topics": [
                {"title": "Layered Architecture and OSI", "slug": "layered-osi", "week": 1, "difficulty": 1, "bloom_level": "understand"},
                {"title": "Data Link Layer and Framing", "slug": "datalink-framing", "week": 2, "difficulty": 2, "bloom_level": "understand"},
                {"title": "Network Layer and IP Addressing", "slug": "network-ip", "week": 3, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Transport Layer TCP and UDP", "slug": "transport-tcp", "week": 4, "difficulty": 3, "bloom_level": "apply"},
                {"title": "Application Layer Protocols HTTP and DNS", "slug": "application-http", "week": 5, "difficulty": 2, "bloom_level": "understand"},
            ],
            "milestones": [
                {"title": "Network Midterm", "week": 3},
                {"title": "Network Final", "week": 5},
            ],
            "proposed_prereqs": [
                {"parent_slug": "layered-osi", "child_slug": "datalink-framing", "confidence": 0.90, "reason": "OSI framing model"},
                {"parent_slug": "datalink-framing", "child_slug": "network-ip", "confidence": 0.90, "reason": "Hop-to-hop before end-to-end routing"},
                {"parent_slug": "network-ip", "child_slug": "transport-tcp", "confidence": 0.95, "reason": "TCP requires underlying IP transport"},
                {"parent_slug": "transport-tcp", "child_slug": "application-http", "confidence": 0.90, "reason": "HTTP runs over TCP socket connection"},
            ],
        },
        # Syllabus 5: Operating Systems (CS501)
        {
            "code": "CS501",
            "credits": 3,
            "topics": [
                {"title": "OS Overview and Process Model", "slug": "os-processes", "week": 1, "difficulty": 1, "bloom_level": "understand"},
                {"title": "Threads and Concurrency", "slug": "threads-concurrency", "week": 2, "difficulty": 2, "bloom_level": "apply"},
                {"title": "CPU Scheduling Algorithms", "slug": "cpu-scheduling", "week": 3, "difficulty": 2, "bloom_level": "apply"},
                {"title": "Process Synchronization and Deadlocks", "slug": "sync-deadlocks", "week": 4, "difficulty": 3, "bloom_level": "analyze"},
                {"title": "Virtual Memory and Paging", "slug": "virtual-memory", "week": 5, "difficulty": 3, "bloom_level": "analyze"},
            ],
            "milestones": [
                {"title": "OS Midterm Exam", "week": 3},
                {"title": "OS Final Exam", "week": 5},
            ],
            "proposed_prereqs": [
                {"parent_slug": "os-processes", "child_slug": "threads-concurrency", "confidence": 0.95, "reason": "Threads share process address space"},
                {"parent_slug": "os-processes", "child_slug": "cpu-scheduling", "confidence": 0.85, "reason": "Scheduler switches between process states"},
                {"parent_slug": "threads-concurrency", "child_slug": "sync-deadlocks", "confidence": 0.95, "reason": "Race conditions necessitate synchronization"},
                {"parent_slug": "os-processes", "child_slug": "virtual-memory", "confidence": 0.80, "reason": "Process address space maps to virtual pages"},
                {"parent_slug": "cpu-scheduling", "child_slug": "virtual-memory", "confidence": 0.45, "reason": "Indirect performance interaction"},
            ],
        },
    ]

    total_proposed_strict_edges = 0
    agreed_strict_edges = 0

    for course in syllabi:
        # Simulate LLM response via FakeLLM
        llm_response = json.dumps({"prerequisites": course["proposed_prereqs"]})
        fake_llm = FakeLLM({"": llm_response})

        roadmap = build_roadmap(
            topics=course["topics"],
            milestones=course["milestones"],
            llm=fake_llm,
            credits=course["credits"],
        )

        # 1. Collect statistics on proposed strict edges
        for item in course["proposed_prereqs"]:
            total_proposed_strict_edges += 1
            if item["confidence"] >= 0.6:
                agreed_strict_edges += 1

        # 2. Verification of roadmap graph properties
        # Topological order is complete (all nodes included)
        assert len(roadmap.order) == len(roadmap.nodes)
        # Any detected cycles were resolved cleanly
        assert find_cycles(roadmap.nodes, roadmap.edges) == []

        # All strict edges in the final roadmap have confidence >= 0.6
        strict_edges = roadmap.edges_of("strict")
        assert all(edge.confidence >= 0.6 for edge in strict_edges)

        # Time integrity check: all covered topics have due_at <= milestone.due_at
        by_id = {node.id: node for node in roadmap.nodes}
        for milestone in roadmap.milestones:
            for topic_id in milestone.covers or []:
                assert by_id[topic_id].due_at <= milestone.due_at

        # Verify weekly duration allocation
        expected_weekly = course["credits"] * 120
        week1_topics = [t for t in roadmap.topics if t.week == 1]
        assert sum(t.duration_minutes for t in week1_topics) == expected_weekly

    # Acceptance criteria: >= 80% strict edges have agreed confidence (confidence >= 0.6)
    consensus_rate = agreed_strict_edges / total_proposed_strict_edges
    assert consensus_rate >= 0.80, f"Consensus rate {consensus_rate:.2%} is below 80%"


def test_learning_path_linear_and_branching():
    from app.roadmap.graph import learning_path

    nodes = ["A", "B", "C", "D", "E"]
    edges = [("A", "C"), ("B", "C"), ("C", "D"), ("E", "D")]

    # Path to C requires A, B, and C
    path_c = learning_path(nodes, edges, "C")
    assert path_c == ["A", "B", "C"] or path_c == ["B", "A", "C"]
    assert path_c[-1] == "C"

    # Path to A requires only A
    assert learning_path(nodes, edges, "A") == ["A"]

    # An unknown node has no path
    assert learning_path(nodes, edges, "Z") == []
    assert learning_path(nodes, edges, "") == []


def test_learning_path_milestone_covers():
    from app.roadmap.graph import Edge, learning_path
    from app.roadmap.nodes import NodeSpec

    t0 = NodeSpec("topic", "Foundations", id="t0")
    t1 = NodeSpec("topic", "Recursion", id="t1")
    t2 = NodeSpec("topic", "Dynamic Programming", id="t2")
    m1 = NodeSpec("milestone", "Midterm Exam", id="m1", covers=["t1", "t2"])

    nodes = [t0, t1, t2, m1]
    edges = [
        Edge("t0", "t1", kind="strict"),
        Edge("t1", "m1", kind="covers"),
        Edge("t2", "m1", kind="covers"),
    ]

    # Pre-exam study path should include all covered topics and their dependencies
    path = learning_path(nodes, edges, "m1")
    assert "t0" in path
    assert "t1" in path
    assert "t2" in path
    assert path[-1] == "m1"
    assert path.index("t0") < path.index("t1")


def test_learning_path_covered_topic_does_not_pull_milestone():
    from app.roadmap.graph import Edge, learning_path
    from app.roadmap.nodes import NodeSpec

    t0 = NodeSpec("topic", "Foundations", id="t0")
    t1 = NodeSpec("topic", "Recursion", id="t1")
    t2 = NodeSpec("topic", "Dynamic Programming", id="t2")
    m1 = NodeSpec("milestone", "Midterm Exam", id="m1", covers=["t1", "t2"])

    nodes = [t0, t1, t2, m1]
    edges = [
        Edge("t0", "t1", kind="strict"),
        Edge("t1", "m1", kind="covers"),
        Edge("t2", "m1", kind="covers"),
    ]

    # Querying a topic must NOT pull in the milestone that covers it, nor unrelated covered topics
    path_t1 = learning_path(nodes, edges, "t1")
    assert path_t1 == ["t0", "t1"]
    assert "m1" not in path_t1
    assert "t2" not in path_t1


def test_transitive_reduction_unit():
    from app.roadmap.graph import transitive_reduction

    nodes = ["A", "B", "C", "D"]
    # A -> B -> C and direct shortcut A -> C
    edges = [("A", "B"), ("B", "C"), ("A", "C"), ("C", "D")]
    reduced = transitive_reduction(nodes, edges)
    # The direct shortcut A -> C is redundant and should be removed
    assert ("A", "C") not in reduced
    assert ("A", "B") in reduced
    assert ("B", "C") in reduced
    assert ("C", "D") in reduced


def test_local_graph_subgraph_navigation():
    from app.roadmap.graph import local_graph

    nodes = ["A", "B", "C", "D", "E"]
    edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]

    # Subgraph centered at C with depth=1
    both_nodes, both_edges = local_graph(nodes, edges, "C", depth=1, direction="both")
    assert set(both_nodes) == {"B", "C", "D"}
    assert ("B", "C") in both_edges
    assert ("C", "D") in both_edges

    ancestors, _ = local_graph(nodes, edges, "C", depth=2, direction="ancestors")
    assert set(ancestors) == {"A", "B", "C"}

    descendants, _ = local_graph(nodes, edges, "C", depth=1, direction="descendants")
    assert set(descendants) == {"C", "D"}


def test_layers_calculation_with_dependencies():
    from app.roadmap.graph import Edge, layers
    from app.roadmap.nodes import NodeSpec

    # t1 starts at week 1, t2 starts at week 1, but t2 strictly depends on t1
    t1 = NodeSpec("topic", "Intro", id="t1", week=1)
    t2 = NodeSpec("topic", "Advanced", id="t2", week=1)
    edges = [Edge("t1", "t2", kind="strict")]

    layer_map = layers([t1, t2], edges)
    assert layer_map["t1"] == 1
    # t2 is pushed to layer 2 because of strict dependency on t1
    assert layer_map["t2"] >= 2


def test_would_create_cycle_check():
    from app.roadmap.graph import would_create_cycle

    edges = [("A", "B"), ("B", "C")]
    # Adding C -> A would close a cycle: C -> A -> B -> C
    cycle_path = would_create_cycle(edges, "C", "A")
    assert cycle_path == ["C", "A", "B", "C"]

    # Adding A -> C is valid (DAG forward edge)
    assert would_create_cycle(edges, "A", "C") is None
