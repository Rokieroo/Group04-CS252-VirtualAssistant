"""The resource-search job: find a node's resources and log what the search cost.

The API enqueues ``search_resources`` with ``{"node_id": ...}``; the worker runs
``app.finder`` (search, vet, curate), links the shown resources to the node and
writes one ``resource_searches`` row plus one ``search_runs`` row per provider
call, so the cost dashboard sees every search (issue #69, spec 11.8).

Results are shared through the 7-day search cache keyed by node signature, so a
second learner of the same node costs nothing and is logged as a cache hit.
"""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curator import Curation
from app.finder import SearchStats, find_resources
from app.llm import get_client
from app.search import SearchService, canonical_url, node_signature
from app.vetting import Learner, Node, SafeFetcher

from .cache import cached_search, store_search
from .jobs import handler
from .models import (
    Course,
    LearningOutcome,
    NodeResource,
    Resource,
    ResourceSearch,
    Roadmap,
    RoadmapNode,
    SearchRun,
    Syllabus,
    User,
)

# Seams for tests and vendor swaps; production uses the configured providers.
make_search = SearchService
make_llm = get_client
make_fetcher = SafeFetcher


def _outcomes(db: Session, course_id: str) -> tuple[str, ...]:
    """Learning outcomes of the course's latest syllabus."""
    latest = (
        select(Syllabus.id)
        .where(Syllabus.course_id == course_id)
        .order_by(Syllabus.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = db.scalars(
        select(LearningOutcome.description)
        .where(LearningOutcome.syllabus_id == latest)
        .order_by(LearningOutcome.code)
    )
    return tuple(rows)


def _search(node: Node, learner: Learner, course: Course, *, db=None) -> tuple[Curation, SearchStats]:
    from app.search.catalog import CatalogSearch
    from app.search.web import WebSearch
    from app.search.youtube import YouTubeSearch
    search = (SearchService(providers=[CatalogSearch(session=db), YouTubeSearch(), WebSearch()])
              if db is not None and make_search is SearchService else make_search())
    with make_fetcher() as fetcher:
        found = find_resources(
            node,
            learner,
            course=course.title,
            search=search,
            llm=make_llm(),
            fetcher=fetcher,
        )
    return found.curation, found.stats


def _link(db: Session, node_id: str, curation: Curation) -> None:
    """Show the curated resources on the node; one ``resources`` row per canonical URL."""
    for resource in curation.resources:
        key = canonical_url(resource.url)
        row = db.scalars(select(Resource).where(Resource.canonical_url == key)).first()
        if row is None:
            # New rows start pending: only the catalog pipeline (#101) verifies.
            row = Resource(
                url=resource.url,
                canonical_url=key,
                title=resource.title,
                provider=resource.provider,
                kind="video" if resource.format == "video" else "article",
                lang=resource.lang,
                domain=resource.domain or None,
                format=resource.format,
                is_free=resource.is_free,
                duration_min=resource.minutes,
                content_hash=resource.content_hash or None,
            )
            db.add(row)
            db.flush()
        link = db.get(NodeResource, (node_id, row.id))
        if link is None:
            db.add(NodeResource(node_id=node_id, resource_id=row.id,
                                relevance_score=resource.score))
        elif link.status == "shown":
            link.relevance_score = resource.score


def _log(
    db: Session,
    node: RoadmapNode,
    user_id: str,
    curation: Curation,
    stats: SearchStats | None,
    now: datetime,
) -> ResourceSearch:
    """One ``resource_searches`` row; its provider calls go to ``search_runs``."""
    search = ResourceSearch(
        node_id=node.id,
        user_id=user_id,
        node_title=node.title,
        status=curation.status,
        cache_hit=int(stats is None),
        kept=len(curation.resources),
        created_at=now,
    )
    if stats is not None:
        search.queries, search.candidates = stats.queries, stats.candidates
        search.vetted, search.llm_calls = stats.vetted, stats.llm_calls
        search.llm_cost_usd, search.search_cost_usd = stats.llm_cost_usd, stats.search_cost_usd
        search.duration_ms = stats.duration_ms
    db.add(search)
    db.flush()
    for run in stats.runs if stats else ():
        db.add(
            SearchRun(
                user_id=user_id,
                query=run.query,  # already PII-filtered by SearchService
                provider=run.provider,
                status=run.status,
                results_count=run.results_count,
                latency_ms=run.latency_ms,
                cost_usd=run.cost_usd,
                search_id=search.id,
                created_at=now,
            )
        )
    return search


@handler("search_resources")
def search_resources(db: Session, payload: dict, now: datetime) -> dict:
    """Find, link and log the resources of ``payload["node_id"]``."""
    node = db.get(RoadmapNode, payload["node_id"])
    if node is None:
        return {"status": "node_deleted"}
    roadmap = db.get(Roadmap, node.roadmap_id)
    course = db.get(Course, roadmap.course_id)
    user = db.get(User, roadmap.user_id)
    from .catalog_repository import refresh_node_sources
    selection = refresh_node_sources(db, [node], roadmap, course, now)[node.id]
    public = [r for r in selection["sources"] if r["kind"] != "user_material" and r["score"] >= 0.8]
    if len(public) >= 3:
        search = ResourceSearch(node_id=node.id, user_id=roadmap.user_id, node_title=node.title,
            status=selection["status"], kept=len(public), candidates=len(public), created_at=now)
        db.add(search)
        db.flush()
        return {"search_id": search.id, "status": selection["status"], "shown": selection["source_count"],
                "cache_hit": False, "cost_usd": 0.0, "catalog_sufficient": True}
    outcomes = _outcomes(db, course.id)
    target = Node(node.title, outcomes, node.duration_minutes)
    learner = Learner(
        langs=tuple(dict.fromkeys((course.language, "vi", "en"))),
        level=course.level,
        k12=user is not None and user.account_level == "k12",
    )

    signature = node_signature(node.title, list(outcomes), course.level, course.language)
    cached = cached_search(db, signature, now)
    if cached is not None:
        curation, stats = Curation.from_dict(cached), None
    else:
        curation, stats = (_search(target, learner, course, db=db) if make_search is SearchService
                           else _search(target, learner, course))
        store_search(db, signature, asdict(curation), now)

    _link(db, node.id, curation)
    search = _log(db, node, roadmap.user_id, curation, stats, now)
    return {
        "search_id": search.id,
        "status": curation.status,
        "shown": len(curation.resources),
        "cache_hit": stats is None,
        "cost_usd": round(search.llm_cost_usd + search.search_cost_usd, 6),
    }
