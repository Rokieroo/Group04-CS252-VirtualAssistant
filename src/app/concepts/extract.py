"""Three-page windows, step two; validate provenance before merging proposals."""
import json
import unicodedata
from difflib import SequenceMatcher
from itertools import groupby
from pathlib import Path
from typing import Literal

from pydantic import Field

from app.ai_data import SLIDE_SYSTEM, Source, StrictModel, data_block
from app.llm import LLMClient


class Concept(StrictModel):
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=5000)
    bloom_level: Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]
    source_pages: list[int] = Field(min_length=1)


class ConceptsResponse(StrictModel):
    concepts: list[Concept]


def normalized_title(title: str) -> str:
    value = unicodedata.normalize("NFKC", title).casefold()
    return " ".join("".join(c if c.isalnum() else " " for c in value).split())


def merge_concepts(concepts: list[dict]) -> list[dict]:
    merged = []
    for concept in concepts:
        match = next((existing for existing in merged if same_concept(existing, concept)), None)
        if match is None:
            merged.append({**concept, "source_pages": sorted(set(concept["source_pages"])),
                           "source_ids": sorted(set(concept.get("source_ids", [])))})
        else:
            match["source_pages"] = sorted(set(match["source_pages"]) | set(concept["source_pages"]))
            match["source_ids"] = sorted(set(match["source_ids"]) | set(concept.get("source_ids", [])))
    return merged


def same_concept(left: dict, right: dict) -> bool:
    return left["slug"] == right["slug"] or SequenceMatcher(
        None, normalized_title(left["title"]), normalized_title(right["title"])
    ).ratio() >= 0.9


def extract_concepts(sources: list[dict], client: LLMClient) -> list[dict]:
    pages = sorted((Source.model_validate(row) for row in sources), key=lambda row: (row.file_name, row.page))
    instruction = (Path(__file__).parent / "prompts/extract_v1.txt").read_text(encoding="utf-8")
    proposals = []
    for _, group in groupby(pages, key=lambda row: row.file_name):
        file_pages = list(group)
        for start in range(0, len(file_pages), 2):
            window = file_pages[start:start + 3]
            if not any(page.text for page in window):
                continue
            prompt = instruction + "\n<slide_text>\n" + data_block([page.model_dump() for page in window]) + "\n</slide_text>"
            result = client.complete(prompt, system=SLIDE_SYSTEM, temperature=0.2, max_tokens=4096,
                                     json_schema=ConceptsResponse.model_json_schema())
            response = ConceptsResponse.model_validate(json.loads(result.text))
            allowed = {page.page for page in window}
            for concept in response.concepts:
                if set(concept.source_pages) <= allowed:
                    proposals.append({**concept.model_dump(), "source_ids": [
                        page.id for page in window if page.page in concept.source_pages
                    ]})
            # Do not call the LLM again for a tail already covered by the last full window.
            if start + 3 >= len(file_pages):
                break
    return merge_concepts(proposals)
