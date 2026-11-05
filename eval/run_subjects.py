"""Measure subject tagging (issue #99): node coverage, resource coverage and precision.

Usage::

    python eval/run_subjects.py           # offline, rules only: the numbers CI enforces
    python eval/run_subjects.py --live    # adds LLM_PROVIDER's embedder and LLM (uses quota)

Nodes: every node roadmap:generate derives from an ``eval/syllabus/*.gold.json``
(one per learning outcome and per assessment) needs at least one accepted topic
label, i.e. confidence >= 0.6. Target: 100% for CSC10014.

Resources: the URLs of ``eval/resources.jsonl`` both raters saw as on-topic (rated
good, or bad only for quality). They are web pages found for a node, not catalog
units, so they carry no course code; the rater's reason stands in for the snippet.
Only accepted labels count. A label is correct when it is a gold topic of the
resource in ``eval/subjects.json`` (its node's topics plus any hand-graded topics of
the page itself), lies under one, or is one's subject or field (true, only coarser);
a sibling topic is wrong. Targets: >= 90% of resources labelled, precision >= 85%.
"strict" counts the node's topics alone; "specific" is the share of resources with a
correct topic label.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.roadmap import derive_nodes, link
from app.taxonomy import NodeText, ResourceText, Tagger, Taxonomy, load_taxonomy

SYLLABI = ROOT / "eval" / "syllabus"
RESOURCES = ROOT / "eval" / "resources.jsonl"
GOLD = ROOT / "eval" / "subjects.json"
ON_TOPIC_BAD = {"low_quality", "inaccurate"}  # bad pages that still teach the node's topic
NODE_TARGET, COVERAGE_TARGET, PRECISION_TARGET = 1.0, 0.9, 0.85


def syllabus_nodes(gold: dict) -> list[NodeText]:
    """The nodes roadmap:generate would build from this parsed syllabus."""
    outcomes = tuple(row["description"] for row in gold["learning_outcomes"])
    specs = link(derive_nodes(
        list(outcomes),
        [(row["name"], row.get("due_week")) for row in gold["assessments"]],
        "\n".join(f"Week {row['week']}: {row['topic']}" for row in gold["weeks"]),
    ))
    titles = {spec.id: spec.title for spec in specs}
    course = f"{gold['course_code']} {gold['course_name']}"
    return [
        NodeText(spec.title, outcomes=outcomes, course=course,
                 covers=tuple(titles[i] for i in spec.covers or () if i in titles))
        for spec in specs
    ]


def node_coverage(tagger: Tagger, gold: dict) -> tuple[int, int]:
    """(nodes with an accepted topic label, nodes)."""
    nodes = syllabus_nodes(gold)
    labelled = sum(
        any(not tag.needs_review and tagger.taxonomy[tag.slug].depth == "topic"
            for tag in tagging.tags)
        for tagging in tagger.tag_nodes(nodes)
    )
    return labelled, len(nodes)


Case = tuple[ResourceText, tuple[str, ...], tuple[str, ...]]  # resource, node gold, graded gold


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
                resource = ResourceText(row.get("title", ""), row["url"], row.get("reason", ""))
                node = tuple(nodes[case["id"]])
                cases.append((resource, node, node + tuple(graded.get(row["url"], ()))))
    return cases


def score(tagger: Tagger, cases: list[Case]) -> dict:
    taxonomy = tagger.taxonomy
    taggings = tagger.tag_resources([resource for resource, _, _ in cases])
    labelled = labels = correct = strict = specific = 0
    for tagging, (_, node, gold) in zip(taggings, cases):
        accepted = [tag.slug for tag in tagging.tags if not tag.needs_review]
        right = [slug for slug in accepted if _correct(taxonomy, slug, gold)]
        labelled += bool(accepted)
        labels += len(accepted)
        correct += len(right)
        strict += sum(_correct(taxonomy, slug, node) for slug in accepted)
        specific += any(taxonomy[slug].depth == "topic" for slug in right)
    return {
        "resources": len(cases),
        "coverage": labelled / len(cases) if cases else 0.0,
        "labels": labels,
        "precision": correct / labels if labels else 0.0,
        "strict": strict / labels if labels else 0.0,
        "specific": specific / len(cases) if cases else 0.0,
    }


def _correct(taxonomy: Taxonomy, slug: str, gold: tuple[str, ...]) -> bool:
    """The gold topic itself, something under it, or something it lies under."""
    return any(slug == g or g in taxonomy.ancestors(slug) or slug in taxonomy.ancestors(g)
               for g in gold)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true",
                        help="use LLM_PROVIDER's embedder and LLM after the rules")
    args = parser.parse_args()
    if args.live:
        from dotenv import load_dotenv

        from app.llm import get_client, get_embedder

        load_dotenv(ROOT / ".env")
        tagger = Tagger(load_taxonomy(), embedder=get_embedder(), llm=get_client())
    else:
        tagger = Tagger(load_taxonomy())

    passed = True
    print("Nodes with an accepted topic label:")
    for path in sorted(SYLLABI.glob("*.gold.json")):
        gold = json.loads(path.read_text(encoding="utf-8"))
        labelled, total = node_coverage(tagger, gold)
        target = gold["course_code"] == "CSC10014"
        passed &= not target or labelled / total >= NODE_TARGET
        print(f"  {gold['course_code']:<9} {labelled}/{total}{'  (target 100%)' if target else ''}")

    result = score(tagger, resource_cases())
    print(f"Resources: {result['resources']}, labelled {result['coverage']:.0%} "
          f"(target {COVERAGE_TARGET:.0%}), {result['labels']} accepted labels")
    print(f"Precision {result['precision']:.0%} (target {PRECISION_TARGET:.0%}), "
          f"{result['strict']:.0%} against node topics alone; "
          f"{result['specific']:.0%} of resources have a correct topic label")
    passed &= result["coverage"] >= COVERAGE_TARGET
    passed &= result["precision"] >= PRECISION_TARGET
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
