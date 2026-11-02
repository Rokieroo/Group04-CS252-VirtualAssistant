import json
import math
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.ai_data import SLIDE_SYSTEM, Source, StrictModel, data_block
from app.llm import LLMClient


class Item(StrictModel):
    type: Literal["mcq", "numeric", "short"]
    prompt: str = Field(min_length=1, max_length=10000)
    choices: list[str] | None = None
    answer: str = Field(min_length=1, max_length=10000)
    rubric: list[str] | None = None
    source_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_type_fields(self):
        if self.type == "mcq":
            if (self.choices is None or len(self.choices) != 4 or
                    any(not value.strip() for value in self.choices) or
                    len({value.strip().casefold() for value in self.choices}) != 4 or
                    self.answer not in self.choices or self.rubric is not None):
                raise ValueError("MCQ requires four unique choices and an answer among them")
        elif self.type == "short":
            if (self.choices is not None or self.rubric is None or not 2 <= len(self.rubric) <= 4 or
                    any(not value.strip() for value in self.rubric)):
                raise ValueError("Short answers require two to four rubric criteria")
        else:
            if self.choices is not None or self.rubric is not None or not math.isfinite(float(self.answer)):
                raise ValueError("Numeric answer must be finite with no choices or rubric")
        return self


class ItemsResponse(StrictModel):
    items: list[Item] = Field(max_length=5)


def generate_items(concept: dict, sources: list[dict], client: LLMClient) -> list[dict]:
    pages = [Source.model_validate(row) for row in sources]
    pages = [page for page in pages if page.text][:3]
    if not pages:
        return []
    instruction = (Path(__file__).parent / "prompts/generate_v1.txt").read_text(encoding="utf-8")
    prompt = instruction + "\n<slide_text>\n" + data_block({
        "concept": concept, "sources": [page.model_dump() for page in pages]
    }) + "\n</slide_text>"
    result = client.complete(prompt, system=SLIDE_SYSTEM, temperature=0.2, max_tokens=4096,
                             json_schema=ItemsResponse.model_json_schema())
    response = ItemsResponse.model_validate(json.loads(result.text))
    allowed = {page.id for page in pages}
    items = [item.model_dump() for item in response.items if item.source_id in allowed]
    if len(items) < 3 or not {"mcq", "short"} <= {item["type"] for item in items}:
        return []
    return items
