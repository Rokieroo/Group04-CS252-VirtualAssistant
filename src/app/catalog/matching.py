"""Rank verified catalog metadata by IDF-weighted term overlap + lexical embeddings (#102).

Topical relevance to the node decides the order; the seven-criteria score only decides
whether a source may be shown. ``CatalogIndex`` prepares the catalog once per request
(title terms, stacked vectors, subject and audience masks), so each node costs array
operations over its pool plus MMR over at most ``CANDIDATES`` sources, not Python work
per (node, source) pair.
"""

from collections import Counter
from functools import lru_cache

import numpy as np

from app.catalog.taxonomy import encode, normalize
from app.retrieval.bm25 import _PositiveIdfBM25
from app.vetting.policy import DomainTier
from app.vetting.score import THRESHOLD, authority, total

NODE_KEYS = ("title", "language", "level")
MIN_COVERAGE = 0.25  # term weight a title must share with the node, of either side's total
MIN_SIMILARITY = 0.3  # a title below that coverage must be this close in meaning
CANDIDATES = 25  # MMR reranks the most topical eligible sources, not the whole pool
REASON = "Matches the stage topic, level, and language; verified source."
# English and (diacritic-free) Vietnamese function words, as ``normalize`` leaves them.
FUNCTION_WORDS = frozenset({
    "a", "an", "and", "or", "of", "the", "in", "on", "to", "for", "with", "by", "at",
    "from", "into", "via", "vs", "as", "is", "are", "its",
    "va", "cua", "cac", "trong", "cho", "voi", "la", "mot", "nhung", "duoc", "ve",
})


def stem(word):
    """Harman's S-stemmer, so "Transactions" matches "Transaction" and "Queries" "Query"."""
    if word.endswith("ies") and not word.endswith(("eies", "aies")):
        return word[:-3] + "y"
    if word.endswith("es") and not word.endswith(("aes", "ees", "oes")):
        return word[:-1]
    if word.endswith("s") and not word.endswith(("us", "ss")):
        return word[:-1]
    return word


@lru_cache(maxsize=16384)
def _title(text):
    """(normalized text, stemmed content terms, lexical vector); titles recur across requests.

    Function words are not terms: in a small pool BM25 gives "and" a positive IDF, and
    a title sharing only "and" with the node then looked fully on topic.
    """
    words = normalize(text)
    vector = np.asarray(encode(text))
    vector.setflags(write=False)  # shared by every caller of the cache
    return words, tuple(stem(w) for w in words.split() if w not in FUNCTION_WORDS), vector


def match_sources(node, resources, *, limit=5):
    """Rank ``verified_resources`` rows for one node context (``node_sources`` builds it).

    The node must carry ``NODE_KEYS``; a missing language or level fails loudly
    rather than defaulting, which would rank sources for the wrong audience.
    Matching several nodes against one catalog: build a ``CatalogIndex`` once.
    """
    return CatalogIndex(resources).match(node, limit=limit)


class CatalogIndex:
    """Verified catalog rows prepared once for every node matched against them."""

    def __init__(self, resources):
        self.rows = [r for r in resources if r.get("verification_status") == "verified"]
        self.position = {r["id"]: i for i, r in enumerate(self.rows)}
        self.titles = [_title(r["title"]) for r in self.rows]
        self.terms = [frozenset(terms) for _, terms, _ in self.titles]
        self.lexical = (
            np.stack([vector for _, _, vector in self.titles])
            if self.rows
            else np.zeros((0, 0))
        )
        self._audiences, self._subjects, self._models, self._bm25 = {}, {}, {}, {}
        self._terms, self._weights = {}, {}

    def match(self, node, *, limit=5, exclude=()):
        """Up to ``limit`` sources for ``node``; ids in ``exclude`` are never chosen."""
        missing = [key for key in NODE_KEYS if not node.get(key)]
        if missing:
            raise ValueError(f"node context is missing {', '.join(missing)}")
        subjects = set(node.get("subjects", []))
        mask = self._audience(node["language"], node["level"]) & self._any_subject(subjects)
        for identifier in exclude:
            if identifier in self.position:
                mask[self.position[identifier]] = False
        pool = np.flatnonzero(mask)
        if not len(pool):
            return []
        # The node's own title is the query: outcomes describe the whole course, so adding
        # them made every source of the course look relevant to every node of it.
        _, query_terms, query_vector = _title(node["title"])
        lexical = self._coverage(pool, query_terms)
        similarity, vector_of = self._similarity(node, pool, query_vector)
        topical = (lexical + similarity) / 2
        textbook = self._textbook(node, pool)
        ranked = []
        for at in np.lexsort((-topical, -textbook.astype(int))):  # textbooks first, then by topic
            if lexical[at] < MIN_COVERAGE and similarity[at] < MIN_SIMILARITY:
                continue  # shares the node's subject but not its topic
            resource = self.rows[pool[at]]
            overlap = _overlap(subjects, resource["subjects"])
            breakdown = {
                "relevance": min(
                    1.0, 0.6 * overlap + 0.2 * float(lexical[at]) + 0.2 * float(similarity[at])
                ),
                "authority": authority(DomainTier(resource.get("tier", 3))),
                "level_fit": 1.0,
                "pedagogy": 0.5,
                "freshness": 0.5,
                "accessibility": 1.0 if resource.get("is_free") else 0.0,
                "community": 0.5,
            }
            score = total(breakdown)
            if score < THRESHOLD:
                continue
            ranked.append(
                {
                    **resource,
                    "score": score,
                    "breakdown": breakdown,
                    "reason": REASON,
                    "textbook": bool(textbook[at]),
                    "_topic": float(topical[at]),
                    "_vector": vector_of(at),
                }
            )
            if len(ranked) == CANDIDATES:
                break
        return [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in _diversify(ranked, limit)
        ]

    def _audience(self, language, level):
        key = (language, level)
        if key not in self._audiences:
            self._audiences[key] = np.array(
                [r.get("lang") == language and r.get("level") == level for r in self.rows],
                dtype=bool,
            )
        return self._audiences[key].copy()

    def _any_subject(self, subjects):
        mask = np.zeros(len(self.rows), dtype=bool)
        for subject in subjects:
            if subject not in self._subjects:
                self._subjects[subject] = np.array(
                    [subject in r.get("subjects", ()) for r in self.rows], dtype=bool
                )
            mask |= self._subjects[subject]
        return mask

    def _coverage(self, pool, terms):
        """IDF-weighted term overlap of each pooled title with the node, in [0, 1].

        Absolute, unlike BM25 divided by the pool's best score: there, a title sharing
        one word out of seven with the node scored 1.0 whenever nothing matched better.
        The larger of the two sides counts, so a short exact title ("Functional
        requirement") still matches a long syllabus node that names it among others.
        """
        model, title_weights = self._pool_weights(pool)
        # The pool says nothing about how rare a term no title has is: average weight.
        weights = {term: model.idf.get(term, model.average_idf) for term in terms}
        shared = np.zeros(len(pool))
        for term, weight in weights.items():
            shared += weight * self._term(term)[pool]
        of_node = shared / max(sum(weights.values()), 1e-9)
        of_title = shared / np.maximum(title_weights, 1e-9)
        return np.maximum(of_node, of_title)

    def _pool_weights(self, pool):
        """The pool's BM25 model and each pooled title's total term weight."""
        model = self._pool_bm25(pool)
        key = pool.tobytes()
        if key not in self._weights:
            self._weights[key] = np.array(
                [sum(model.idf.get(t, 0.0) for t in self.terms[i]) for i in pool]
            )
        return model, self._weights[key]

    def _term(self, term):
        """Which rows' titles contain ``term``; shared by every node that uses it."""
        if term not in self._terms:
            self._terms[term] = np.array([term in terms for terms in self.terms], dtype=bool)
        return self._terms[term]

    def _pool_bm25(self, pool):
        """Positive IDF over the pool's titles, shared by the nodes with the same pool.

        Okapi's IDF drops to zero or below in the few-title pools the subject filter
        leaves, where a term in every title would then weigh nothing.
        """
        key = pool.tobytes()
        if key not in self._bm25:
            self._bm25[key] = _PositiveIdfBM25(
                [self.titles[i][1] or ("_",) for i in pool]
            )
        return self._bm25[key]

    def _similarity(self, node, pool, query_vector):
        """Similarity of each pooled source to the node, and the vector it was taken from.

        A source embedded by the node's model compares semantically; any other source
        compares by the lexical vectors of the two titles.
        """
        lexical = self.lexical[pool]
        similarity = lexical @ query_vector
        semantic, matrix = np.zeros(len(pool), dtype=bool), None
        model = node.get("vector_model") if node.get("vector") is not None else None
        if model is not None:
            has, matrix = self._model(model)
            node_vector = np.asarray(node["vector"])
            if node_vector.shape[0] == matrix.shape[1]:
                semantic = has[pool]
                similarity[semantic] = matrix[pool[semantic]] @ node_vector

        def vector_of(at):
            return matrix[pool[at]] if semantic[at] else lexical[at]

        return np.maximum(similarity, 0), vector_of

    def _model(self, model):
        """(rows embedded by ``model``, their vectors stacked; zeros elsewhere)."""
        if model not in self._models:
            found = {
                i: np.asarray(r["vector"])
                for i, r in enumerate(self.rows)
                if r.get("vector") is not None and r.get("vector_model") == model
            }
            size = Counter(v.shape[0] for v in found.values()).most_common(1)
            width = size[0][0] if size else 0
            has = np.zeros(len(self.rows), dtype=bool)
            matrix = np.zeros((len(self.rows), width))
            for i, vector in found.items():
                if vector.shape[0] == width:
                    has[i], matrix[i] = True, vector
            self._models[model] = has, matrix
        return self._models[model]

    def _textbook(self, node, pool):
        textbooks = [normalize(title) for title in node.get("textbooks", [])]
        if not textbooks:
            return np.zeros(len(pool), dtype=bool)
        return np.array(
            [
                bool(words) and any(words in title for title in textbooks)
                for words, _, _ in (self.titles[i] for i in pool)
            ],
            dtype=bool,
        )


def _overlap(node_subjects, source_subjects):
    """How fully a source and a node share subjects, from whichever side is narrower.

    A weekly node names several concepts (#94): a source that teaches one of them is
    wholly on topic, though it covers only part of the node.
    """
    shared = len(node_subjects.intersection(source_subjects))
    return shared / max(1, min(len(node_subjects), len(source_subjects)))


def _similar(left, right):
    return float(left @ right) if left.shape == right.shape else 0.0


def _diversify(ranked, limit):
    """MMR: relevance to the node minus redundancy with what is chosen, two per domain."""
    chosen, per_domain, formats = [], Counter(), set()
    # Each candidate's highest similarity to a chosen source; only a new pick can raise
    # it, so one pick costs one product per candidate instead of one per chosen source.
    redundancy = dict.fromkeys(range(len(ranked)), 0.0)

    def mmr(index):
        resource = ranked[index]
        fmt = resource.get("format") or ""
        diversity = 0.05 if fmt and fmt not in formats else 0
        # MMR's relevance term is similarity to the query; the seven-criteria score
        # only decided eligibility, or authority alone would rank off-topic pages first.
        return (
            bool(resource.get("textbook")),
            0.7 * resource["_topic"] - 0.3 * redundancy[index] + diversity,
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
        per_domain[best.get("domain") or ""] += 1
        if best.get("format"):
            formats.add(best["format"])
        for i in redundancy:
            redundancy[i] = max(redundancy[i], _similar(ranked[i]["_vector"], best["_vector"]))
    return chosen
