"""What the uploaded syllabi need from the catalog (#98 step 4, ADR 004 section 1).

The catalog is filled on demand: a syllabus becomes the roadmap nodes
``roadmap:generate`` would derive, each node becomes its subject labels (#99),
and the labels of every syllabus, in priority order, are what the connectors
are asked for.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.catalog.taxonomy import tag_node
from app.roadmap import derive_nodes, link


@dataclass(frozen=True)
class SyllabusDemand:
    course: str  # code and name, e.g. "CSC10014 Problem Framing ..."
    outcomes: tuple[str, ...]
    assessments: tuple[tuple[str, int | None], ...]
    raw_text: str = ""

    @classmethod
    def from_gold(cls, gold: dict) -> "SyllabusDemand":
        """A benchmark syllabus of ``eval/syllabus/*.gold.json`` (#66)."""
        return cls(
            course=f"{gold['course_code']} {gold['course_name']}",
            outcomes=tuple(row["description"] for row in gold["learning_outcomes"]),
            assessments=tuple((row["name"], row.get("due_week")) for row in gold["assessments"]),
            raw_text="\n".join(f"Week {row['week']}: {row['topic']}" for row in gold["weeks"]),
        )


def node_subjects(demand: SyllabusDemand) -> list[tuple[str, frozenset[str]]]:
    """(title, accepted subject labels) of each roadmap node, in roadmap order."""
    specs = link(derive_nodes(list(demand.outcomes), list(demand.assessments), demand.raw_text))
    titles = {spec.id: spec.title for spec in specs}
    return [
        (
            spec.title,
            frozenset(
                tag.subject_id
                for tag in tag_node(
                    {"title": spec.title},
                    course=demand.course,
                    outcomes=demand.outcomes,
                    covers=[titles[i] for i in spec.covers or () if i in titles],
                )
                if not tag.needs_review
            ),
        )
        for spec in specs
    ]


def priority_batches(
    demands: Iterable[SyllabusDemand],
) -> list[tuple[SyllabusDemand, list[str]]]:
    """Each syllabus with the labels no earlier syllabus asked for, in the given order.

    Ingesting batch by batch fills the first syllabus (CSC10014) before the
    benchmark ones, so a quota or network failure later costs only the later ones.
    """
    asked: set[str] = set()
    batches = []
    for demand in demands:
        needed = sorted(set().union(*(labels for _, labels in node_subjects(demand))) - asked)
        asked.update(needed)
        batches.append((demand, needed))
    return batches
