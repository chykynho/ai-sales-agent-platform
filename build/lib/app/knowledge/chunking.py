from __future__ import annotations

from dataclasses import dataclass
import re

from app.knowledge.parsers import ExtractedSection


@dataclass(slots=True)
class TextChunk:
    content: str
    page_number: int | None


def chunk_sections(
    sections: list[ExtractedSection],
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for section in sections:
        text = re.sub(r"[ \t]+", " ", section.text).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            if end < len(text):
                candidate = text.rfind("\n", start, end)
                if candidate <= start + max_chars // 2:
                    candidate = text.rfind(". ", start, end)
                    if candidate > start + max_chars // 2:
                        candidate += 1
                if candidate > start + max_chars // 2:
                    end = candidate
            content = text[start:end].strip()
            if content:
                chunks.append(TextChunk(content=content, page_number=section.page_number))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_chars)
    return chunks
