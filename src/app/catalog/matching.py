"""Rank verified catalog metadata with BM25 + reusable lexical embeddings (#102)."""

from collections import Counter

from rank_bm25 import BM25Okapi

from app.catalog.taxonomy import cosine, encode, normalize
from app.vetting.policy import DomainTier
from app.vetting.score import authority, total


def match_sources(node, resources, *, limit=5):
    subjects = set(node.get("subjects", []))
    pool = [
        r
        for r in resources
        if r.get("verification_status") == "verified"
        and r.get("lang") == node["language"]
        and r.get("level") == node["level"]
        and subjects.intersection(r.get("subjects", []))
    ]
    if not pool:
        return []
    corpus = [normalize(r["title"]).split() or ["_"] for r in pool]
    query = normalize(node["title"] + " " + " ".join(node.get("outcomes", [])))
    bm25 = BM25Okapi(corpus).get_scores(query.split())
    maximum = max(max(bm25), 0.001)
    vector = node.get("vector") or encode(query)
    ranked = []
    for resource, lexical in zip(pool, bm25, strict=True):
        resource_vector = resource.get("vector") or encode(resource["title"])
        similarity = max(0, cosine(vector, resource_vector))
        overlap = len(subjects.intersection(resource["subjects"])) / max(
            1, len(subjects)
        )
        relevance = min(
            1.0, 0.6 * overlap + 0.2 * max(0, lexical) / maximum + 0.2 * similarity
        )
        breakdown = {
            "relevance": relevance,
            "authority": authority(DomainTier(resource.get("tier", 3))),
            "level_fit": 1.0,
            "pedagogy": 0.5,
            "freshness": 0.5,
            "accessibility": 1.0 if resource.get("is_free") else 0.0,
            "community": 0.5,
        }
        score = total(breakdown)
        if score >= 0.65:
            ranked.append(
                {
                    **resource,
                    "_match_vector": resource_vector,
                    "score": score,
                    "breakdown": breakdown,
                    "reason": "Khớp chủ đề, trình độ và ngôn ngữ của chặng; nguồn đã được xác minh.",
                    "textbook": any(
                        normalize(resource["title"]) in normalize(title)
                        for title in node.get("textbooks", [])
                    ),
                }
            )
    chosen, per_domain = [], Counter()
    while ranked and len(chosen) < limit:
        allowed = [r for r in ranked if per_domain[r["domain"]] < 2]
        if not allowed:
            break

        def mmr(resource):
            redundancy = max(
                (
                    max(0, cosine(resource["_match_vector"], other["_match_vector"]))
                    for other in chosen
                ),
                default=0,
            )
            diversity = (
                0.05 if resource["format"] not in {r["format"] for r in chosen} else 0
            )
            return (
                bool(resource["textbook"]),
                0.7 * resource["score"] - 0.3 * redundancy + diversity,
                resource["id"],
            )

        best = max(allowed, key=mmr)
        chosen.append(best)
        per_domain[best["domain"]] += 1
        ranked.remove(best)
    return chosen
