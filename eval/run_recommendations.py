"""Benchmark the unified resource recommender across 5 syllabi in offline mode (issue #160).

Usage::

    python eval/run_recommendations.py          # 3-config comparison + red-team + invariants
    python eval/run_recommendations.py --json   # machine-readable JSON report

Compares three configurations on the 5 benchmark syllabi (50 week nodes total):

1. ``db_only``: verified catalog resources only (``match_sources``).
2. ``db_plus_external``: catalog + recorded external pages, through ``vet`` + ``curate``.
3. ``db_plus_external_plus_feedback``: as 2, with learner votes passed to ``vet``.

What the offline numbers can and cannot say. The external pages are synthetic fixtures
and the judge is a stand-in (``ContentJudge``) that never sees a label: relevance is how
many of the node's words a page contains. So Precision@5 / nDCG@5 of configs 2-3 show
whether the pipeline keeps on-topic fixture pages and drops off-topic ones, not how good
real recommendations are. The votes of config 3 are the fixture labels themselves (an
oracle), so config 3 is an upper bound on what feedback can add. Real quality needs
recorded provider responses with blind labels, or an ``--llm`` run; neither is here.

The pass/fail gate is therefore only what offline can prove about the product itself:
pirated domains, adult pages for K-12 learners and prompt-injection pages stay out of
the top 5, and external items are never ``verified``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.catalog.matching import match_sources
from app.catalog.taxonomy import cosine, encode, normalize, tag_node, tag_resource
from app.curator import curate
from app.llm import LLMClient, LLMResult
from app.search import Candidate, canonical_url
from app.vetting import Learner, Node, read_document, vet
from app.vetting.fetch import FetchResult
from app.vetting.judge import MIN_QUOTE_CHARS, strip_commands
from app.vetting.policy import default_policy
from assistant.backend.catalog_repository import verified_resources
from assistant.backend.database import Database
from assistant.backend.models import Course, Roadmap, RoadmapNode, User, utcnow
from assistant.backend.recommendations_repository import (
    get_or_generate_node_recommendations,
)

SYLLABUS_DIR = ROOT / "eval" / "syllabus"
RESOURCES_PATH = ROOT / "eval" / "resources.jsonl"
INJECTIONS_DIR = ROOT / "eval" / "fixtures" / "redteam" / "injections"
PIRATED_PATH = ROOT / "eval" / "fixtures" / "redteam" / "pirated_urls.jsonl"

BENCHMARK_SYLLABI = [
    ("01_csc10014_problem_framing.gold.json", "CSC10014"),
    ("02_cs102_database_systems.gold.json", "CS102"),
    ("03_cs201_data_structures.gold.json", "CS201"),
    ("04_cs202_operating_systems.gold.json", "CS202"),
    ("05_cs203_computer_networks.gold.json", "CS203"),
]

# Spec targets, reported next to the numbers; not a gate offline (see the module docstring).
PRECISION_TARGET = 0.80
NDCG_TARGET = 0.75
REDTEAM_NODE = "Algorithms: problem framing and binary search"
_STOPWORDS = {"and", "the", "for", "with", "chang"}


@dataclass(frozen=True)
class ConfigMetrics:
    config: str
    total_nodes: int
    covered_nodes: int
    coverage_rate: float
    precision_at_5: float
    ndcg_at_5: float
    avg_formats_in_top5: float


@dataclass(frozen=True)
class RedTeamReport:
    injection_pages_tested: int
    injection_leaked_to_top5: int
    injection_directives_stripped: int  # pages whose directive strip_commands removed
    pirated_urls_tested: int
    pirated_leaked_to_top5: int
    k12_adult_pages_tested: int
    k12_adult_leaked_to_top5: int
    external_marked_verified: int


def _block(prompt: str, name: str) -> str:
    match = re.search(rf"<{name}>(.*?)</{name}>", prompt, flags=re.DOTALL)
    return match.group(1) if match else ""


def _topic_words(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) >= 3 and w not in _STOPWORDS}


class ContentJudge(LLMClient):
    """Offline stand-in for the judge model; it never sees a label or a fixture role.

    It reads only what the real judge is shown (``<learning_goal>`` and the
    ``<page_text>`` that ``strip_commands`` left): relevance is the share of the node's
    words on the page (0-4), the quote is the first verbatim line long enough to count.
    """

    def complete(self, prompt: str, **kwargs: Any) -> LLMResult:
        return LLMResult(text=self.generate(prompt), input_tokens=0, output_tokens=0,
                         cost_usd=0.0)

    def generate(self, prompt: str, **kwargs: Any) -> str:
        goal = next((line for line in _block(prompt, "learning_goal").splitlines()
                     if line.startswith("Chặng:")), "")
        page = _block(prompt, "page_text")
        wanted = _topic_words(goal)
        share = len(wanted & set(normalize(page).split())) / len(wanted) if wanted else 0.0
        quote = next((" ".join(line.split()) for line in page.splitlines()
                      if len(" ".join(line.split())) >= MIN_QUOTE_CHARS + 4), "")
        return json.dumps({
            "relevance": round(4 * share),
            "level_fit": 3,
            "pedagogy": 3,
            "evidence_quote": quote[:120],
            "reason": f"{share:.0%} of the node's words appear on the page.",
        })


class FixtureFetcher:
    """Serves recorded pages; anything else is a 404."""

    def __init__(self, responses: dict[str, FetchResult]) -> None:
        self._responses = {canonical_url(url): page for url, page in responses.items()}
        self.policy = default_policy()

    def fetch(self, url: str) -> FetchResult:
        return self._responses.get(canonical_url(url)) or FetchResult(
            url=url, final_url=url, status=404, content_type="text/html", body=b"")


def _page(url: str, html: str) -> FetchResult:
    return FetchResult(url=url, final_url=url, status=200, content_type="text/html",
                       body=html.encode("utf-8"))


def _article(title: str, body: str, head: str = "") -> str:
    return (f"<html><head><title>{title}</title>{head}</head>"
            f"<body><article><h1>{title}</h1><p>{body}</p></article></body></html>")


def ndcg_at_5(shown_good: list[bool], good_available: int) -> float:
    """Binary-relevance nDCG@5 against the ideal ordering with all good items first."""
    dcg = sum(1 / math.log2(rank + 2) for rank, good in enumerate(shown_good[:5]) if good)
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(good_available, 5)))
    return dcg / ideal if ideal else 0.0


def _domain(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _infer_format(url: str, kind: str) -> str:
    if kind == "video" or "youtube.com" in url or "youtu.be" in url:
        return "video"
    if kind in ("interactive", "exercise"):
        return "exercise"
    return "reading"


def _load_db_pool(
    resources_path: Path,
    syllabi_nodes: list[tuple[str, int, str]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], set[str]], dict[str, FetchResult]]:
    """The verified catalog pool (resources labelled ``good`` in #106), each assigned to the
    syllabus week closest to its case's node, and a page for each."""
    db_pool: list[dict[str, Any]] = []
    good_by_node: dict[tuple[str, int], set[str]] = {}
    db_responses: dict[str, FetchResult] = {}

    nodes_by_course: dict[str, list[tuple[int, str]]] = {}
    for code, week, topic in syllabi_nodes:
        nodes_by_course.setdefault(code, []).append((week, topic))

    for line in resources_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        node = case["node"]
        code = node.get("course_code", "")
        if code not in nodes_by_course:
            continue
        case_vec = encode(node["title"])
        best_week = max(nodes_by_course[code], key=lambda wt: cosine(case_vec, encode(wt[1])))[0]

        good_urls = good_by_node.setdefault((code, best_week), set())
        for idx, row in enumerate(case["resources"]):
            if row.get("label") != "good":
                continue
            url = row["url"]
            good_urls.add(canonical_url(url))
            title = f"{node['title']} - {row.get('reason', 'Verified Guide').capitalize()}"
            tags = tag_resource({"title": title, "description": node["title"]})
            db_pool.append({
                "id": f"{case['id']}-db-{idx}",
                "title": title,
                "url": url,
                "canonical_url": canonical_url(url),
                "domain": _domain(url),
                "tier": 1 if row.get("category") in ("academic", "authoritative") else 2,
                "verification_status": "verified",
                "lang": row.get("lang", "en"),
                "level": "undergrad",
                "format": _infer_format(url, row.get("kind", "article")),
                "is_free": True,
                "subjects": {t.subject_id for t in tags if t.confidence >= 0.4} or {"cs-general"},
                "vector": None,
                "vector_model": None,
            })
            # The page speaks of its own case's topic, never of the queried week.
            db_responses[url] = _page(url, _article(
                node["title"], f"{title}: verified catalog source covering {node['title']}."))
    return db_pool, good_by_node, db_responses


def _build_external_payloads(
    syllabi_nodes: list[tuple[str, int, str]],
    good_by_node: dict[tuple[str, int], set[str]],
    base_responses: dict[str, FetchResult],
) -> tuple[dict[tuple[str, int], list[Candidate]], dict[str, FetchResult],
           dict[tuple[str, int], set[str]], dict[tuple[str, int], str]]:
    """Per node: five on-topic pages from providers the product has (#157), one thin
    outline (labelled not good) and one off-topic page. Labels are kept here and never
    reach the judge; nothing on a page names its label."""
    candidates_by_node: dict[tuple[str, int], list[Candidate]] = {}
    responses: dict[str, FetchResult] = dict(base_responses)
    good_by_ext_node: dict[tuple[str, int], set[str]] = {}
    outline_by_node: dict[tuple[str, int], str] = {}

    for code, week, topic in syllabi_nodes:
        slug = f"{code.lower()}-w{week}"
        on_topic = [
            (f"https://ocw.mit.edu/courses/{slug}/exercises/", "mit_ocw", "exercise",
             f"{topic} — Problem Set"),
            (f"https://openstax.org/books/{slug}/pages/1-introduction", "openstax", "article",
             f"{topic} — Textbook Chapter"),
            (f"https://en.wikipedia.org/wiki/{slug}", "wikipedia", "article", topic),
            (f"https://en.wikibooks.org/wiki/{slug}", "wikibooks", "article",
             f"{topic} — Wikibook"),
            (f"https://www.youtube.com/watch?v={slug}-lecture", "youtube", "video",
             f"{topic} — Lecture"),
        ]
        outline = f"https://quick-study-notes.example.org/{slug}-overview"
        off_topic = f"https://deals.example.com/{slug}"
        cands = [Candidate(url, title, provider, kind, "en", snippet=topic)
                 for url, provider, kind, title in on_topic]
        cands += [
            Candidate(outline, f"{topic} — Overview", "web", "article", "en", snippet=topic),
            Candidate(off_topic, "Weekly deals", "web", "article", "en", snippet="deals"),
        ]
        candidates_by_node[(code, week)] = cands
        outline_by_node[(code, week)] = outline
        good_by_ext_node[(code, week)] = (
            {canonical_url(url) for url, *_ in on_topic} | good_by_node.get((code, week), set()))

        for url, _provider, _kind, title in on_topic:
            responses[url] = _page(url, _article(
                title, f"This university module covers {topic} with worked examples and "
                       f"exercises, then reviews the main results of {topic}."))
        responses[outline] = _page(outline, _article(
            f"{topic} — Overview", f"{topic}: a brief outline of the basic definitions of {topic}."))
        responses[off_topic] = _page(off_topic, _article(
            "Weekly deals", "Phones, laptops and headphones on sale this week, with free shipping."))

    return candidates_by_node, responses, good_by_ext_node, outline_by_node


def _syllabi_nodes() -> list[tuple[str, int, str]]:
    nodes = []
    for filename, code in BENCHMARK_SYLLABI:
        gold = json.loads((SYLLABUS_DIR / filename).read_text(encoding="utf-8"))
        nodes += [(code, int(w["week"]), w["topic"]) for w in gold.get("weeks", [])]
    return nodes


def evaluate_three_configs() -> tuple[list[ConfigMetrics], dict[str, Any]]:
    """Run all 3 recommender configurations on the 5 benchmark syllabi."""
    syllabi_nodes = _syllabi_nodes()
    db_pool, good_by_node, db_responses = _load_db_pool(RESOURCES_PATH, syllabi_nodes)
    ext_cands_by_node, responses, good_by_ext_node, outline_by_node = _build_external_payloads(
        syllabi_nodes, good_by_node, db_responses)
    fetcher = FixtureFetcher(responses)
    llm = ContentJudge()
    learner = Learner(langs=("en", "vi"), level="undergrad")

    db_hits_by_node: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for code, week, topic in syllabi_nodes:
        subjects = {t.subject_id for t in tag_node({"title": topic}, outcomes=[code])}
        context = {"title": topic, "language": "en", "level": "undergrad",
                   "subjects": subjects or {"cs-general"}, "outcomes": [code], "textbooks": []}
        db_hits_by_node[(code, week)] = match_sources(context, db_pool, limit=5)

    results: list[ConfigMetrics] = []
    per_syllabus: dict[str, dict[str, dict[str, list[float]]]] = {}
    for config_name in ("db_only", "db_plus_external", "db_plus_external_plus_feedback"):
        precisions: list[float] = []
        ndcgs: list[float] = []
        formats_counts: list[int] = []
        covered = 0

        for code, week, topic in syllabi_nodes:
            db_hits = db_hits_by_node[(code, week)]
            if config_name == "db_only":
                shown_urls = [r["canonical_url"] for r in db_hits]
                shown_formats = {r["format"] for r in db_hits}
                good_set = good_by_node.get((code, week), set())
            else:
                good_set = good_by_ext_node[(code, week)]
                db_cands = [Candidate(r["url"], r["title"], "catalog",
                                      "video" if r["format"] == "video" else "article", r["lang"])
                            for r in db_hits]
                ratings = None
                if config_name == "db_plus_external_plus_feedback":
                    # Oracle votes: learners agree with the fixture labels (an upper bound).
                    ratings = {url: (18, 20) for url in good_set}
                    ratings[outline_by_node[(code, week)]] = (0, 25)
                vetted = vet([*db_cands, *ext_cands_by_node[(code, week)]],
                             Node(title=topic, outcomes=(code,), est_minutes=60), learner,
                             llm=llm, fetcher=fetcher, ratings=ratings)  # type: ignore[arg-type]
                top5 = curate(vetted.resources, est_minutes=60).resources[:5]
                shown_urls = [canonical_url(r.url) for r in top5]
                shown_formats = {r.format for r in top5}

            if not shown_urls:
                continue
            covered += 1
            marks = [url in good_set for url in shown_urls[:5]]
            p5, n5 = sum(marks) / len(marks), ndcg_at_5(marks, len(good_set))
            precisions.append(p5)
            ndcgs.append(n5)
            formats_counts.append(len(shown_formats))
            row = per_syllabus.setdefault(config_name, {}).setdefault(
                code, {"p5": [], "n5": [], "fmt": []})
            row["p5"].append(p5)
            row["n5"].append(n5)
            row["fmt"].append(len(shown_formats))

        total = len(syllabi_nodes)
        results.append(ConfigMetrics(
            config=config_name,
            total_nodes=total,
            covered_nodes=covered,
            coverage_rate=round(covered / total, 3) if total else 0.0,
            precision_at_5=round(sum(precisions) / len(precisions), 3) if precisions else 0.0,
            ndcg_at_5=round(sum(ndcgs) / len(ndcgs), 3) if ndcgs else 0.0,
            avg_formats_in_top5=(round(sum(formats_counts) / len(formats_counts), 2)
                                 if formats_counts else 0.0),
        ))
    return results, per_syllabus


def _external_verified_count() -> int:
    """External suggestions of the real repository must never be ``verified``."""
    db_mgr = Database("sqlite://")
    db_mgr.create_schema()
    try:
        with db_mgr.sessions() as db:
            user = User(email="eval-provenance@example.com", password_hash="x", name="Eval")
            db.add(user)
            db.flush()
            course = Course(title="CS Eval", owner_id=user.id)
            db.add(course)
            db.flush()
            roadmap = Roadmap(course_id=course.id, user_id=user.id, title="Eval Track")
            db.add(roadmap)
            db.flush()
            node = RoadmapNode(roadmap_id=roadmap.id, type="topic",
                               title="Distributed Consensus", week=1)
            db.add(node)
            db.commit()
            recs = get_or_generate_node_recommendations(db, node, user.id, limit=5)
            verified_refs = {f"catalog:{row['id']}" for row in verified_resources(db, utcnow())}
            return sum(
                1 for rec in recs
                if (rec.kind == "external" or rec.resource_ref.startswith("external:"))
                and (getattr(rec, "verification_status", None) == "verified"
                     or rec.resource_ref in verified_refs)
            )
    finally:
        db_mgr.engine.dispose()


def evaluate_external_redteam() -> RedTeamReport:
    """Pirated and adult pages are on-topic, so only the domain policy and the K-12 filter
    can keep them out; injection pages are the fixtures as written."""
    node = Node(title=REDTEAM_NODE, outcomes=("CLO1",), est_minutes=60)
    on_topic = (f"{REDTEAM_NODE}: worked examples of binary search and problem framing for "
                f"algorithms students.")
    responses: dict[str, FetchResult] = {}

    inj_files = sorted(INJECTIONS_DIR.glob("*.html"))
    inj_cands = []
    stripped = 0
    for i, path in enumerate(inj_files):
        url = f"https://untrusted-external.example.org/inj-{i}.html"
        candidate = Candidate(url, f"External Note {i}", "web", "article", "en")
        responses[url] = FetchResult(url=url, final_url=url, status=200,
                                     content_type="text/html", body=path.read_bytes())
        text = read_document(candidate, responses[url]).text
        stripped += strip_commands(text) != text.strip()
        inj_cands.append(candidate)

    pirated_rows = [json.loads(line) for line in PIRATED_PATH.read_text(encoding="utf-8").splitlines()
                    if line.strip()]
    pirated_cands = []
    for i, row in enumerate(pirated_rows):
        pirated_cands.append(Candidate(row["url"], f"Algorithms textbook {i}", "web", "article", "en"))
        responses[row["url"]] = _page(row["url"], _article(f"Algorithms textbook {i}", on_topic))

    adult_urls = [f"https://external-media.example.org/adult-{i}" for i in range(1, 4)]
    adult_cands = []
    for i, url in enumerate(adult_urls):
        adult_cands.append(Candidate(url, f"Algorithms notes {i}", "web", "article", "en"))
        responses[url] = _page(url, _article(f"Algorithms notes {i}", on_topic,
                                             head='<meta name="rating" content="adult">'))

    control = "https://cs.example.edu/algorithms/notes"
    responses[control] = _page(control, _article("Algorithms notes", on_topic))
    fetcher = FixtureFetcher(responses)
    llm = ContentJudge()
    adult = Learner(langs=("en", "vi"), level="university")
    k12 = Learner(langs=("en", "vi"), level="k12", k12=True)

    def top5(cands: list[Candidate], learner: Learner) -> int:
        vetted = vet(cands, node, learner, llm=llm, fetcher=fetcher)  # type: ignore[arg-type]
        return len(curate(vetted.resources, est_minutes=60).resources[:5])

    # Control: the same on-topic page from an ordinary host must reach the top 5, or zero
    # leaks would only mean the pages were never good enough to be shown.
    assert top5([Candidate(control, "Algorithms notes", "web", "article", "en")], k12) == 1

    return RedTeamReport(
        injection_pages_tested=len(inj_files),
        injection_leaked_to_top5=top5(inj_cands, adult),
        injection_directives_stripped=stripped,
        pirated_urls_tested=len(pirated_rows),
        pirated_leaked_to_top5=top5(pirated_cands, adult),
        k12_adult_pages_tested=len(adult_urls),
        k12_adult_leaked_to_top5=top5(adult_cands, k12),
        external_marked_verified=_external_verified_count(),
    )


def passed(redteam: RedTeamReport) -> bool:
    return (redteam.injection_leaked_to_top5 == 0 and redteam.pirated_leaked_to_top5 == 0
            and redteam.k12_adult_leaked_to_top5 == 0 and redteam.external_marked_verified == 0)


def print_report(configs: list[ConfigMetrics], redteam: RedTeamReport) -> None:
    print("## Unified Resource Recommender Benchmark (Issue #160, Offline Mode)\n")
    print("Synthetic external pages and a label-blind stand-in judge: configs 2-3 check the "
          "pipeline, not real quality; config 3 uses oracle votes (upper bound).\n")
    print("| Configuration | Total Nodes | Covered Nodes | Node Coverage | Precision@5 | nDCG@5 "
          "| Avg Formats in Top-5 |")
    print("| :--- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for c in configs:
        print(f"| `{c.config}` | {c.total_nodes} | {c.covered_nodes} | {c.coverage_rate * 100:.1f}% "
              f"| {c.precision_at_5:.3f} | {c.ndcg_at_5:.3f} | {c.avg_formats_in_top5:.2f} |")
    print("\n### External Red-Team & Provenance Invariants\n")
    print(f"- Prompt-injection pages: {redteam.injection_pages_tested} -> leaked to top-5: "
          f"**{redteam.injection_leaked_to_top5}**; directive removed by `strip_commands`: "
          f"{redteam.injection_directives_stripped}/{redteam.injection_pages_tested}")
    print(f"- Pirated URLs (on-topic pages): {redteam.pirated_urls_tested} -> leaked to top-5: "
          f"**{redteam.pirated_leaked_to_top5}**")
    print(f"- K-12 adult pages (on-topic): {redteam.k12_adult_pages_tested} -> leaked to top-5: "
          f"**{redteam.k12_adult_leaked_to_top5}**")
    print(f"- External items marked `verified`: **{redteam.external_marked_verified}**")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="output JSON report")
    args = parser.parse_args()

    configs, _ = evaluate_three_configs()
    redteam = evaluate_external_redteam()
    ok = passed(redteam)
    if args.json:
        print(json.dumps({"configs": [asdict(c) for c in configs], "redteam": asdict(redteam),
                          "passed": ok}, indent=2))
    else:
        print_report(configs, redteam)
        print(f"\nSummary: {'RED-TEAM AND INVARIANTS PASSED' if ok else 'BENCHMARK FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
