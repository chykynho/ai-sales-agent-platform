from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


@dataclass(slots=True)
class ExtractedSection:
    text: str
    page_number: int | None = None


def extract_sections(filename: str, content_type: str, data: bytes) -> list[ExtractedSection]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        reader = PdfReader(BytesIO(data))
        result: list[ExtractedSection] = []
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                result.append(ExtractedSection(text=text, page_number=i + 1))
        return result

    if suffix == ".docx" or content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        doc = DocxDocument(BytesIO(data))
        text = "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        return [ExtractedSection(text)] if text else []

    if suffix in {".txt", ".md", ".markdown"} or content_type.startswith("text/"):
        text = data.decode("utf-8-sig").strip()
        return [ExtractedSection(text)] if text else []

    raise ValueError("Unsupported file type. Use PDF, DOCX, TXT or Markdown.")
