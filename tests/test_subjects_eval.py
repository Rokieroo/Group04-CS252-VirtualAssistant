"""Subject tagging meets #99's acceptance targets offline (eval/run_subjects.py)."""

import json
import sys
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "eval"
sys.path.insert(0, str(EVAL))

from run_subjects import (
    COVERAGE_TARGET,
    GOLD,
    NODE_TARGET,
    PRECISION_TARGET,
    SYLLABI,
    correct,
    node_coverage,
    resource_cases,
    score,
)

from app.catalog.taxonomy import subjects


def test_gold_uses_real_labels():
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    known = {row["id"] for row in subjects()}
    labels = [s for group in ("nodes", "resources") for ids in gold[group].values() for s in ids]
    assert set(labels) <= known


def test_csc10014_nodes_all_get_a_topic():
    gold = json.loads(next(SYLLABI.glob("01_csc10014*.gold.json")).read_text(encoding="utf-8"))
    labelled, total = node_coverage(gold)
    assert labelled / total >= NODE_TARGET


def test_resources_meet_coverage_and_precision():
    result = score(resource_cases())
    assert result["resources"] >= 100
    assert result["coverage"] >= COVERAGE_TARGET
    assert result["precision"] >= PRECISION_TARGET


def test_a_sibling_topic_is_wrong_and_an_ancestor_is_coarse_but_right():
    assert correct("ds", ("ds.trees",))
    assert correct("ds.trees", ("ds",))
    assert not correct("ds.lists", ("ds.trees",))
