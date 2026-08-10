"""Text chunking for document ingestion.

Recursive split on progressively weaker separators so a chunk boundary lands on
a paragraph break where possible and mid-word only as a last resort. Each chunk
records the page range it came from so a retrieved fact can be traced back.
"""

from __future__ import annotations

from dataclasses import dataclass

_SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class Chunk:
    """One unit of text handed to the memory graph."""

    index: int
    text: str
    first_page: int
    last_page: int


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    """Split one string into overlapping windows on the best available boundary."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = -1
            for sep in _SEPARATORS:
                found = text.rfind(sep, start + size // 2, end)
                if found != -1:
                    cut = found + len(sep)
                    break
            if cut != -1:
                end = cut
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def chunk_pages(pages: list[str], size: int, overlap: int) -> list[Chunk]:
    """Chunk a document page-by-page, preserving page provenance.

    Chunking per page keeps the page range exact. Empty pages (no text layer)
    are skipped, so a scanned PDF produces zero chunks rather than noise.
    """
    chunks: list[Chunk] = []
    index = 0
    for page_number, page_text in enumerate(pages, start=1):
        for piece in _split_text(page_text, size, overlap):
            chunks.append(
                Chunk(
                    index=index,
                    text=piece,
                    first_page=page_number,
                    last_page=page_number,
                )
            )
            index += 1
    return chunks
