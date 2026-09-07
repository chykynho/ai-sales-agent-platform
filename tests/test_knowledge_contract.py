from app.core.config import settings
from app.knowledge.chunking import chunk_sections
from app.knowledge.parsers import ExtractedSection

def test_chunking_overlap_and_nonempty():
    text="A"*1500
    chunks=chunk_sections([ExtractedSection(text)],max_chars=1200,overlap_chars=200)
    assert len(chunks)>=2
    assert all(c.content for c in chunks)

def test_embedding_dimensions_configured_for_pgvector():
    assert settings.embedding_dimensions == 1536
