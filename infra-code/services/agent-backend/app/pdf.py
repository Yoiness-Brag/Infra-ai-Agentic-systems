"""PDF validation and text extraction.

Uploaded bytes are attacker-influenced, so the content type reported by the
client is ignored: the magic bytes decide. Encrypted documents are rejected
because extraction would silently yield nothing, and the page count is capped
so a single upload cannot queue an unbounded number of LLM extraction calls.
"""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger("agent_backend.pdf")

_PDF_MAGIC = b"%PDF-"


class InvalidPdfError(ValueError):
    """The upload is not a usable PDF."""


def looks_like_pdf(data: bytes) -> bool:
    """True when the payload starts with the PDF magic bytes."""
    return data[:5] == _PDF_MAGIC


def extract_pages(data: bytes, max_pages: int) -> list[str]:
    """Return the text of each page.

    Raises :class:`InvalidPdfError` for anything that is not a readable,
    unencrypted PDF within the page cap. Pages with no text layer come back as
    empty strings and are dropped by the caller; a scanned PDF therefore yields
    nothing rather than failing, which the caller reports as an empty ingest.
    """
    if not looks_like_pdf(data):
        raise InvalidPdfError("payload is not a PDF (bad magic bytes)")

    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, OSError, ValueError) as exc:
        raise InvalidPdfError(f"cannot parse PDF: {exc.__class__.__name__}") from exc

    if reader.is_encrypted:
        raise InvalidPdfError("encrypted PDFs are not supported")

    page_count = len(reader.pages)
    if page_count == 0:
        raise InvalidPdfError("PDF has no pages")
    if page_count > max_pages:
        raise InvalidPdfError(f"PDF has {page_count} pages, limit is {max_pages}")

    pages: list[str] = []
    for index, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - one bad page must not fail the doc
            logger.warning(
                "page extraction failed",
                extra={"page": index, "err": exc.__class__.__name__},
            )
            pages.append("")
    return pages


def page_count(data: bytes) -> int:
    """Return the page count without extracting text."""
    if not looks_like_pdf(data):
        raise InvalidPdfError("payload is not a PDF (bad magic bytes)")
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise InvalidPdfError(f"cannot parse PDF: {exc.__class__.__name__}") from exc
