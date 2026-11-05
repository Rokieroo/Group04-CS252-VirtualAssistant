"""Untrusted text goes into named data blocks it cannot close early (spec 12.3)."""

from __future__ import annotations

import re


class PromptBlocks:
    """The block tags our prompts use; data is stripped of every one of them."""

    def __init__(self, *tags: str):
        self.tags = frozenset(tags)
        names = "|".join(re.escape(tag) for tag in sorted(self.tags))
        self._tag = re.compile(rf"</?\s*({names})\s*>", re.IGNORECASE)

    def clean(self, value: str) -> str:
        return self._tag.sub("", value)

    def wrap(self, tag: str, value: str) -> str:
        if tag not in self.tags:
            raise ValueError(f"unknown prompt block <{tag}>")
        return f"<{tag}>\n{self.clean(value)}\n</{tag}>"


# Shared by every prompt so text in one block can never fake another block's tags.
BLOCKS = PromptBlocks(
    "document_text", "known_concepts", "previous_concepts", "previous_notes", "candidates",
    "concept", "learning_goal", "page_text", "syllabus_anchors", "taxonomy", "tag_items",
)
