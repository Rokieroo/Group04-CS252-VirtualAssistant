"""nDCG@5 in eval/run_resources.py (#106)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from run_resources import ndcg_at_5


def test_ndcg_rewards_good_resources_shown_first():
    assert ndcg_at_5([True, True, False], good_available=2) == 1.0
    assert 0 < ndcg_at_5([False, True], good_available=1) < 1.0
    assert ndcg_at_5([False, True, True], 2) < ndcg_at_5([True, True, False], 2)


def test_ndcg_is_zero_when_nothing_good_was_shown_or_exists():
    assert ndcg_at_5([False, False], good_available=3) == 0.0
    assert ndcg_at_5([True], good_available=0) == 0.0


def test_ndcg_only_counts_the_top_five():
    assert ndcg_at_5([False] * 5 + [True], good_available=1) == 0.0
