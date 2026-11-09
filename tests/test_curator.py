"""Issue #62: MMR selection, diversity rules, curate-or-abstain and feedback replacement."""

from dataclasses import asdict

import pytest

from app.curator import Curation, curate, lexical_similarity, replace
from app.vetting import ScoredResource


def resource(name, score=0.8, *, domain=None, fmt="reading", minutes=10, text=None,
             quote="A grounded quote that the page really contains.", pinned=False):
    return ScoredResource(
        url=f"https://{domain or name + '.example'}/{name}",
        title=name,
        provider="web",
        format=fmt,
        lang="en",
        domain=domain or f"{name}.example",
        is_free=True,
        minutes=minutes,
        score=score,
        breakdown={},
        reason="",
        evidence_quote=quote,
        content_hash=name,
        excerpt=text if text is not None else f"{name} unique words {name}",
        pinned=pinned,
    )


def names(curation):
    return [r.title for r in curation.resources]


def test_best_five_are_shown_and_the_rest_kept_in_reserve():
    pool = [resource(f"r{i}", 0.9 - i * 0.02) for i in range(8)]
    result = curate(pool)
    assert result.status == "ready"
    assert names(result) == ["r0", "r1", "r2", "r3", "r4"]
    assert [r.title for r in result.reserve] == ["r5", "r6", "r7"]


def test_curate_or_abstain_never_fills_with_weak_or_ungrounded_resources():
    pool = [resource("good", 0.9), resource("weak", 0.6), resource("ungrounded", 0.9, quote="")]
    result = curate(pool)
    assert result.status == "insufficient"
    assert names(result) == ["good"]
    assert result.gaps[0].startswith("Chưa tìm được đủ nguồn")


def test_teacher_pins_lead_and_skip_the_domain_limit():
    pins = [resource(f"pin{i}", 0.0, domain="ocw.mit.edu", pinned=True) for i in range(2)]
    pool = [resource(f"mit{i}", 0.9, domain="ocw.mit.edu") for i in range(3)]
    pool += [resource("other", 0.7)]
    result = curate(pool, pinned=pins)
    assert names(result)[:2] == ["pin0", "pin1"]
    # Two pins plus the two-per-domain limit: the third MIT page waits in reserve.
    assert names(result)[2:] == ["mit0", "mit1", "other"]


def test_at_most_two_resources_per_domain():
    pool = [resource(f"same{i}", 0.95, domain="a.example") for i in range(4)]
    pool += [resource("b", 0.7), resource("c", 0.7)]
    result = curate(pool)
    assert sum(r.domain == "a.example" for r in result.resources) == 2


def test_top_five_mixes_reading_video_and_exercise_when_available():
    pool = [resource(f"read{i}", 0.95) for i in range(6)]
    pool += [resource("video", 0.7, fmt="video"), resource("drill", 0.66, fmt="exercise")]
    result = curate(pool)
    assert {r.format for r in result.resources} == {"reading", "video", "exercise"}
    assert len(result.resources) == 5
    assert result.gaps == []


def test_mmr_prefers_a_different_resource_over_a_near_copy():
    pool = [
        resource("a", 0.90, text="recursion base case factorial example"),
        resource("copy", 0.89, text="recursion base case factorial example"),
        resource("fresh", 0.85, text="tree traversal stack frames"),
    ]
    result = curate(pool, top_k=2)
    assert names(result) == ["a", "fresh"]


def test_total_minutes_stay_within_one_and_a_half_times_the_estimate():
    pool = [resource("long", 0.95, minutes=50), resource("short", 0.9, minutes=10),
            resource("mid", 0.85, minutes=20)]
    result = curate(pool, est_minutes=40)  # budget 60 minutes
    assert names(result) == ["long", "short"]
    assert sum(r.minutes for r in result.resources) <= 60


def test_not_helpful_brings_up_the_next_candidate_without_a_new_search():
    pool = [resource(f"r{i}", 0.9 - i * 0.02) for i in range(7)]
    result = replace(curate(pool), "https://r1.example/r1")
    assert names(result) == ["r0", "r2", "r3", "r4", "r5"]
    assert [r.title for r in result.reserve] == ["r6"]
    with pytest.raises(KeyError):
        replace(result, "https://r1.example/r1")


def test_replacement_keeps_the_domain_limit():
    pool = [resource("a1", 0.9, domain="a.example"), resource("a2", 0.88, domain="a.example"),
            resource("b", 0.8), resource("a3", 0.86, domain="a.example"), resource("c", 0.7)]
    shown = curate(pool, top_k=3)
    assert names(shown) == ["a1", "a2", "b"]
    assert names(replace(shown, "https://b.example/b")) == ["a1", "a2", "c"]


def test_curation_round_trips_through_json_storage():
    result = curate([resource("x", 0.9), resource("y", 0.8)], est_minutes=30)
    assert Curation.from_dict(asdict(result)) == result


def test_lexical_similarity_bounds():
    same = resource("x", text="recursion base case")
    assert lexical_similarity(same, same) == pytest.approx(1.0)
    assert lexical_similarity(resource("a", text="alpha"), resource("b", text="beta")) == 0.0

def test_lexical_similarity_handles_none_and_empty_text():
    r1_none = ScoredResource(
        url="https://example.com/1",
        title="",
        provider="web",
        format="reading",
        lang="en",
        domain="example.com",
        is_free=True,
        minutes=10,
        score=0.8,
        breakdown={},
        reason="",
        evidence_quote="quote",
        content_hash="h1",
        excerpt=None,
    )
    r2_none = ScoredResource(
        url="https://example.com/2",
        title="",
        provider="web",
        format="reading",
        lang="en",
        domain="example.com",
        is_free=True,
        minutes=10,
        score=0.8,
        breakdown={},
        reason="",
        evidence_quote="quote",
        content_hash="h2",
        excerpt=None,
    )
    assert lexical_similarity(r1_none, r2_none) == 0.0

