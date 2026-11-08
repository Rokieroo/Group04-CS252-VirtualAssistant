"""Measure subject tagging (issue #99) against its acceptance criteria.

Usage::

    python eval/run_subjects.py

Runs the offline path (rules, then the lexical vector) that tags nodes and
resources when no embedding model is configured; no network, no quota.

Nodes: every node roadmap:generate derives from an ``eval/syllabus/*.gold.json``
(one per learning outcome and per assessment) needs at least one accepted topic
label: depth 3 and not ``needs_review``. Target: 100% for CSC10014.

Resources: the URLs of ``eval/resources.jsonl`` both raters saw as on-topic (rated
good, or bad only for quality). They are web pages found for a node, not catalog
units, so they carry no course code. The dataset keeps no page titles: the URL's
path stands in for the title and the rater's reason for a description. Only
accepted labels count. A label is correct when it is a gold label
of the resource in ``eval/subjects.json`` (its node's labels plus any hand-graded
labels of the page itself), lies under one, or is one's ancestor (true, only
coarser); a sibling is wrong. Targets: >= 90% of resources labelled, precision
>= 85%. "strict" scores against the node's labels alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.catalog.taxonomy import subjects, tag_node, tag_resource
from app.roadmap import derive_nodes, link

SYLLABI = ROOT / "eval" / "syllabus"
RESOURCES = ROOT / "eval" / "resources.jsonl"
GOLD = ROOT / "eval" / "subjects.json"
ON_TOPIC_BAD = {"low_quality", "inaccurate"}  # bad pages that still teach the node's topic
NODE_TARGET, COVERAGE_TARGET, PRECISION_TARGET = 1.0, 0.9, 0.85

Case = tuple[dict, tuple[str, ...], tuple[str, ...]]  # resource, node gold, graded gold


def ancestors(subject_id: str) -> set[str]:
    parents = {row["id"]: row.get("parent_id") for row in subjects()}
    found = set()
    while parents.get(subject_id):
        subject_id = parents[subject_id]
        found.add(subject_id)
    return found


def node_coverage(gold: dict) -> tuple[int, int]:
    """(nodes with an accepted topic label, nodes) for the roadmap of one syllabus."""
    outcomes = [row["description"] for row in gold["learning_outcomes"]]
    specs = link(derive_nodes(
        outcomes,
        [(row["name"], row.get("due_week")) for row in gold["assessments"]],
        "\n".join(f"Week {row['week']}: {row['topic']}" for row in gold["weeks"]),
    ))
    depth = {row["id"]: row["depth"] for row in subjects()}
    titles = {spec.id: spec.title for spec in specs}
    course = f"{gold['course_code']} {gold['course_name']}"
    labelled = sum(
        any(not tag.needs_review and depth[tag.subject_id] == 3
            for tag in tag_node({"title": spec.title}, course=course, outcomes=outcomes,
                                covers=[titles[i] for i in spec.covers or () if i in titles]))
        for spec in specs
    )
    return labelled, len(specs)


def resource_cases(path: Path = RESOURCES, gold_path: Path = GOLD) -> list[Case]:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    nodes, graded = gold["nodes"], gold.get("resources", {})
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        for row in case["resources"]:
            if row["label"] == "good" or row.get("category") in ON_TOPIC_BAD:
                resource = {"title": urlparse(row["url"]).path,
                            "description": row.get("reason", "")}
                node = tuple(nodes[case["id"]])
                cases.append((resource, node, node + tuple(graded.get(row["url"], ()))))
    return cases


def correct(subject_id: str, gold: tuple[str, ...]) -> bool:
    """The gold label itself, something under it, or something it lies under."""
    return any(subject_id == g or g in ancestors(subject_id) or subject_id in ancestors(g)
               for g in gold)


def score(cases: list[Case]) -> dict:
    labelled = labels = right = strict = 0
    for resource, node, gold in cases:
        accepted = [tag.subject_id for tag in tag_resource(resource) if not tag.needs_review]
        labelled += bool(accepted)
        labels += len(accepted)
        right += sum(correct(s, gold) for s in accepted)
        strict += sum(correct(s, node) for s in accepted)
    return {
        "resources": len(cases),
        "coverage": labelled / len(cases) if cases else 0.0,
        "labels": labels,
        "precision": right / labels if labels else 0.0,
        "strict": strict / labels if labels else 0.0,
    }


def main() -> int:
    passed = True
    print("Nodes with an accepted topic label:")
    for path in sorted(SYLLABI.glob("*.gold.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        labelled, total = node_coverage(gold)
        target = gold["course_code"] == "CSC10014"
        passed &= not target or labelled / total >= NODE_TARGET
        print(f"  {gold['course_code']:<9} {labelled}/{total}{'  (target 100%)' if target else ''}")

    result = score(resource_cases())
    print(f"Resources: {result['resources']}, labelled {result['coverage']:.0%} "
          f"(target {COVERAGE_TARGET:.0%}), {result['labels']} accepted labels")
    print(f"Precision {result['precision']:.0%} (target {PRECISION_TARGET:.0%}), "
          f"{result['strict']:.0%} against node labels alone")
    passed &= result["coverage"] >= COVERAGE_TARGET
    passed &= result["precision"] >= PRECISION_TARGET
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
