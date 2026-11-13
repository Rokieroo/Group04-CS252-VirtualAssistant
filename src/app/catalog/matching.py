"""Rank verified catalog metadata with BM25 + reusable lexical embeddings (#102)."""

from collections import Counter

from rank_bm25 import BM25Okapi

from app.catalog.taxonomy import cosine, encode, normalize
from app.vetting.policy import DomainTier
from app.vetting.score import authority, total

NODE_KEYS = ("title", "language", "level")


def match_sources(node, resources, *, limit=5):
    """Rank ``verified_resources`` rows for one node context (``node_sources`` builds it).

    The node must carry ``NODE_KEYS``; a missing language or level fails loudly
    rather than defaulting, which would rank sources for the wrong audience.
    """
    missing = [key for key in NODE_KEYS if not node.get(key)]
    if missing:
        raise ValueError(f"node context is missing {', '.join(missing)}")
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
    lexical_vector = encode(query)
    ranked = []
    for resource, lexical in zip(pool, bm25, strict=True):
        compatible = (
            node.get("vector") is not None
            and resource.get("vector") is not None
            and node.get("vector_model") == resource.get("vector_model")
        )
        vector = node["vector"] if compatible else lexical_vector
        resource_vector = (
            resource["vector"] if compatible else encode(resource["title"])
        )
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
                        (norm_t := normalize(title))
                        and (norm_r := normalize(resource["title"]))
                        and norm_r in norm_t
                        for title in node.get("textbooks", [])
                    ),
                }
            )
    chosen, per_domain, formats = [], Counter(), set()
    # Each candidate's highest similarity to a chosen source; only a new pick can raise
    # it, so one pick costs one cosine per candidate instead of one per chosen source.
    redundancy = dict.fromkeys(range(len(ranked)), 0.0)

    def mmr(index):
        resource = ranked[index]
        fmt = resource.get("format") or ""
        diversity = 0.05 if fmt and fmt not in formats else 0
        return (
            bool(resource.get("textbook")),
            0.7 * resource["score"] - 0.3 * redundancy[index] + diversity,
            resource["id"],
        )

    while redundancy and len(chosen) < limit:
        allowed = [i for i in redundancy if per_domain[ranked[i].get("domain") or ""] < 2]
        if not allowed:
            break
        pick = max(allowed, key=mmr)
        del redundancy[pick]
        best = ranked[pick]
        chosen.append(best)
        domain = best.get("domain") or ""
        per_domain[domain] += 1
        best_fmt = best.get("format") or ""
        if best_fmt:
            formats.add(best_fmt)
        for i in redundancy:
            similarity = cosine(ranked[i]["_match_vector"], best["_match_vector"])
            redundancy[i] = max(redundancy[i], similarity)
    return chosen
