"""The resource-search job: find a node's resources and log what the search cost.

The API enqueues ``search_resources`` with ``{"node_id": ...}``; the worker runs
``app.finder`` (search, vet, curate), links the shown resources to the node and
writes one ``resource_searches`` row plus one ``search_runs`` row per provider
call, so the cost dashboard sees every search (issue #69, spec 11.8).

Results are shared through the 7-day search cache keyed by node signature, so a
second learner of the same node costs nothing and is logged as a cache hit. Each
external provider stays within its daily quota (``provider_quota``, issue #161);
past it the search answers from the catalog alone, and ``refresh_searches`` renews
studied nodes' results each night before they expire.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.curator import Curation
from app.finder import SearchStats, find_resources
from app.llm import get_client
from app.recommend import STRONG, needs_external
from app.search import (
    CatalogSearch,
    SearchService,
    WebSearch,
    YouTubeSearch,
    canonical_url,
    node_signature,
)
from app.vetting import Learner, Node, SafeFetcher

from .cache import cached_search, store_search
from .catalog_jobs import tonight
from .costs import failing_providers
from .jobs import enqueue, handler
from .models import (
    Course,
    Job,
    LearningOutcome,
    NodeResource,
    Recommendation,
    Resource,
    ResourceSearch,
    Roadmap,
    RoadmapNode,
    SearchCacheEntry,
    SearchRun,
    Syllabus,
    User,
)
from .provider_quota import remaining_calls

log = logging.getLogger(__name__)


def default_search(db: Session, quota: Mapping[str, int]) -> SearchService:
    """The production providers, catalog first; ``quota`` caps the external ones."""
    return SearchService([CatalogSearch(session=db), YouTubeSearch(), WebSearch()], quota=quota)


# Seams for tests and vendor swaps; production uses the configured providers.
make_search = default_search
make_llm = get_client
make_fetcher = SafeFetcher

SEARCHES_PER_HOUR = 20  # per learner: searches cost provider quota and judge calls
REFRESH = "refresh_searches"
REFRESH_BATCH = 50  # searches queued a night: bounds the quota one refresh can spend
STUDIED = timedelta(days=7)  # a node recommended this week is still being studied
REFRESH_AHEAD = timedelta(days=1)  # renew results that would expire before the next night


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


def _search(
    node: Node, learner: Learner, course: Course, search: SearchService
) -> tuple[Curation, SearchStats]:
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
    curated = {}
    for resource in curation.resources:  # ranked, so the first copy of a URL wins
        curated.setdefault(canonical_url(resource.url), resource)
    if not curated:
        return
    rows = {
        row.canonical_url: row
        for row in db.scalars(
            select(Resource).where(Resource.canonical_url.in_(curated))
        )
    }
    for key, resource in curated.items():
        if key not in rows:
            # New rows start pending: only the catalog pipeline (#101) verifies.
            rows[key] = Resource(
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
            db.add(rows[key])
    db.flush()  # ids for the new rows
    links = {
        link.resource_id: link
        for link in db.scalars(
            select(NodeResource).where(
                NodeResource.node_id == node_id,
                NodeResource.resource_id.in_([row.id for row in rows.values()]),
            )
        )
    }
    for key, resource in curated.items():
        link = links.get(rows[key].id)
        if link is None:
            db.add(
                NodeResource(
                    node_id=node_id,
                    resource_id=rows[key].id,
                    relevance_score=resource.score,
                )
            )
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


def search_signature(
    db: Session,
    node: RoadmapNode,
    course: Course,
    *,
    outcomes: Sequence[str] | None = None,
) -> str:
    """The key of the node's shared 7-day search cache (spec 11.8).

    Callers that already read the course's outcomes pass them to skip a second query.
    """
    if outcomes is None:
        outcomes = _outcomes(db, course.id)
    return node_signature(node.title, list(outcomes), course.level, course.language)


def learner_for(course: Course, user: User | None) -> Learner:
    """Who the course's resources are for: course language first, never personal data."""
    return Learner(
        langs=tuple(dict.fromkeys((course.language, "vi", "en"))),
        level=course.level,
        k12=user is not None and user.account_level == "k12",
    )


def recent_searches(db: Session, user_id: str, now: datetime) -> int:
    """Resource searches the learner queued in the last hour, asked for or automatic."""
    return db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.user_id == user_id,
            Job.kind == "search_resources",
            Job.created_at > now - timedelta(hours=1),
        )
    )


def request_search(db: Session, node_id: str, user_id: str, now: datetime) -> Job | None:
    """Queue the node's external search at most once a day, within the hourly budget."""
    if recent_searches(db, user_id, now) >= SEARCHES_PER_HOUR:
        return None
    return enqueue(
        db,
        "search_resources",
        {"node_id": node_id},
        now=now,
        user_id=user_id,
        dedupe_key=f"search_resources:{node_id}:{now.date().isoformat()}",
    )


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
    if not needs_external(selection["sources"]):
        public = [r for r in selection["sources"] if r["kind"] != "user_material" and r["score"] >= STRONG]
        search = ResourceSearch(node_id=node.id, user_id=roadmap.user_id, node_title=node.title,
            status=selection["status"], kept=len(public), candidates=len(public), created_at=now)
        db.add(search)
        db.flush()
        return {"search_id": search.id, "status": selection["status"], "shown": selection["source_count"],
                "cache_hit": False, "cost_usd": 0.0, "catalog_sufficient": True}
    outcomes = _outcomes(db, course.id)
    target = Node(node.title, outcomes, node.duration_minutes)
    learner = learner_for(course, user)

    signature = search_signature(db, node, course, outcomes=outcomes)
    # A nightly refresh searches again even while the results it renews are still valid.
    cached = None if payload.get("refresh") else cached_search(db, signature, now)
    if cached is not None:
        curation, stats = Curation.from_dict(cached), None
    else:
        service = make_search(db, remaining_calls(db, roadmap.user_id, now))
        curation, stats = _search(target, learner, course, service)
        # Results a quota cut short would stand in for a full search for 7 days.
        if not getattr(service, "last_skipped", None):
            store_search(db, signature, asdict(curation), now)

    _link(db, node.id, curation)
    search = _log(db, node, roadmap.user_id, curation, stats, now)
    if stats is not None:
        for failing in failing_providers(db, now):
            log.warning("provider=%(provider)s failed %(errors)d of %(calls)d calls "
                        "in the last hour", failing)
    return {
        "search_id": search.id,
        "status": curation.status,
        "shown": len(curation.resources),
        "cache_hit": stats is None,
        "cost_usd": round(search.llm_cost_usd + search.search_cost_usd, 6),
    }


def schedule_nightly(db: Session, now: datetime) -> None:
    """Queue tonight's refresh once; called daily, the dedupe key makes repeats no-ops."""
    enqueue(db, REFRESH, now=now, dedupe_key=f"{REFRESH}:{now.date().isoformat()}",
            run_after=tonight(now))


@handler(REFRESH)
def refresh_searches(db: Session, payload: dict, now: datetime) -> dict:
    """Search again for studied nodes whose shared results expire before the next night.

    Daytime requests then read fresh results from the cache instead of waiting for a
    search. Nodes with the same signature share one search; the most recently
    recommended nodes go first, and at most ``REFRESH_BATCH`` searches are queued.
    """
    studied = db.scalars(
        select(RoadmapNode)
        .join(Recommendation, Recommendation.node_id == RoadmapNode.id)
        .where(Recommendation.created_at >= now - STUDIED)
        .group_by(RoadmapNode.id)
        .order_by(func.max(Recommendation.created_at).desc())
    ).all()
    outcomes: dict[str, tuple[str, ...]] = {}
    queued = 0
    for node in studied:
        course = db.get(Course, db.get(Roadmap, node.roadmap_id).course_id)
        if course.id not in outcomes:
            outcomes[course.id] = _outcomes(db, course.id)
        signature = search_signature(db, node, course, outcomes=outcomes[course.id])
        entry = db.get(SearchCacheEntry, signature)
        if entry is None or entry.expires_at > now + REFRESH_AHEAD:
            continue  # never searched (the catalog sufficed), or still fresh tomorrow
        job = enqueue(
            db,
            "search_resources",
            {"node_id": node.id, "refresh": True},
            now=now,
            dedupe_key=f"{REFRESH}:{signature}:{now.date().isoformat()}",
        )
        queued += job is not None
        if queued == REFRESH_BATCH:
            break
    return {"queued": queued}
