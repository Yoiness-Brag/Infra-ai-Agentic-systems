"""Document upload API.

``POST /documents`` stores the PDF in MinIO, records it in Postgres and queues
an ingestion job that writes chunks into the FalkorDB memory graph. Upload is
idempotent on the SHA-256 of the bytes, so re-uploading the same file returns
the existing document instead of duplicating the graph partition.
"""

from __future__ import annotations

import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from .auth import verify_token
from .config import Settings, get_settings
from .memory import MemoryStore
from .pdf import InvalidPdfError, looks_like_pdf, page_count
from .sessions import SessionStore
from .storage import ObjectStore

logger = logging.getLogger("agent_backend.documents")

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentAccepted(BaseModel):
    """Response for an accepted (or already-present) upload."""

    document_id: str
    job_id: str | None = None
    filename: str
    bytes: int
    page_count: int | None = None
    state: str = Field(description="queued | duplicate")


class DocumentStatus(BaseModel):
    """Ingestion status for one document."""

    document_id: str
    filename: str
    bytes: int
    page_count: int | None = None
    state: str | None = None
    chunks_total: int | None = None
    chunks_done: int | None = None
    error: str | None = None


class DocumentSummary(BaseModel):
    """One row of the document list."""

    document_id: str
    filename: str
    bytes: int
    page_count: int | None = None
    state: str | None = None
    chunks_total: int | None = None
    chunks_done: int | None = None


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentAccepted,
    summary="Upload a PDF for ingestion into the memory graph",
    responses={
        202: {"description": "Upload accepted; ingestion queued"},
        200: {"description": "Identical content already uploaded"},
        400: {"description": "Not a valid PDF"},
        401: {"description": "Missing or invalid bearer token"},
        413: {"description": "Upload exceeds MAX_UPLOAD_BYTES"},
    },
)
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="PDF file"),
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> DocumentAccepted:
    """Store a PDF in MinIO and queue it for graph ingestion."""
    sessions: SessionStore = request.app.state.sessions
    storage: ObjectStore = request.app.state.storage

    data = await _read_bounded(file, settings.max_upload_bytes)

    if not looks_like_pdf(data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only PDF uploads are accepted (magic-byte check failed)",
        )
    try:
        pages = page_count(data)
    except InvalidPdfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if pages > settings.max_pdf_pages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PDF has {pages} pages, limit is {settings.max_pdf_pages}",
        )

    sha256 = hashlib.sha256(data).hexdigest()
    filename = _safe_filename(file.filename)

    existing = await sessions.find_document_by_hash(settings.workload_app, subject, sha256)
    if existing is not None:
        return DocumentAccepted(
            document_id=str(existing["document_id"]),
            filename=str(existing["filename"]),
            bytes=int(existing["bytes"]),
            page_count=existing["page_count"],
            state="duplicate",
        )

    document_id = str(uuid.uuid4())
    group_id = settings.document_group_id(subject, document_id)
    object_key = f"{settings.workload_app}/{subject}/{document_id}.pdf"

    await storage.put(object_key, data, "application/pdf")

    created = await sessions.create_document(
        document_id=document_id,
        app=settings.workload_app,
        owner_subject=subject,
        filename=filename,
        content_sha256=sha256,
        bytes=len(data),
        page_count=pages,
        object_key=object_key,
        group_id=group_id,
    )
    if created is None:
        await storage.delete(object_key)
        again = await sessions.find_document_by_hash(settings.workload_app, subject, sha256)
        if again is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="document insert raced"
            )
        return DocumentAccepted(
            document_id=str(again["document_id"]),
            filename=str(again["filename"]),
            bytes=int(again["bytes"]),
            page_count=again["page_count"],
            state="duplicate",
        )

    job_id = await sessions.create_job(str(uuid.uuid4()), document_id)
    logger.info(
        "document queued",
        extra={"document_id": document_id, "pages": pages, "bytes": len(data)},
    )
    return DocumentAccepted(
        document_id=document_id,
        job_id=job_id,
        filename=filename,
        bytes=len(data),
        page_count=pages,
        state="queued",
    )


@router.get(
    "",
    response_model=list[DocumentSummary],
    summary="List documents owned by the caller",
)
async def list_documents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> list[DocumentSummary]:
    """Return this subject's documents, newest first."""
    sessions: SessionStore = request.app.state.sessions
    rows = await sessions.list_documents(settings.workload_app, subject, limit, offset)
    return [
        DocumentSummary(
            document_id=str(r["document_id"]),
            filename=str(r["filename"]),
            bytes=int(r["bytes"]),
            page_count=r["page_count"],
            state=r["state"],
            chunks_total=r["chunks_total"],
            chunks_done=r["chunks_done"],
        )
        for r in rows
    ]


@router.get(
    "/{document_id}",
    response_model=DocumentStatus,
    summary="Ingestion status for one document",
    responses={404: {"description": "No such document for this caller"}},
)
async def get_document(
    document_id: str,
    request: Request,
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> DocumentStatus:
    """Return one document's metadata and ingestion progress."""
    sessions: SessionStore = request.app.state.sessions
    row = await sessions.get_document(settings.workload_app, subject, _uuid(document_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return DocumentStatus(
        document_id=str(row["document_id"]),
        filename=str(row["filename"]),
        bytes=int(row["bytes"]),
        page_count=row["page_count"],
        state=row["state"],
        chunks_total=row["chunks_total"],
        chunks_done=row["chunks_done"],
        error=row["error"],
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document, its object and its graph partition",
    responses={404: {"description": "No such document for this caller"}},
)
async def delete_document(
    document_id: str,
    request: Request,
    subject: str = Depends(verify_token),
    settings: Settings = Depends(get_settings),
) -> None:
    """Remove the Postgres rows, the MinIO object and the graph partition."""
    sessions: SessionStore = request.app.state.sessions
    storage: ObjectStore = request.app.state.storage
    memory: MemoryStore = request.app.state.memory

    row = await sessions.delete_document(settings.workload_app, subject, _uuid(document_id))
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    try:
        await storage.delete(str(row["object_key"]))
    except Exception as exc:  # noqa: BLE001 - the row is already gone
        logger.warning("object delete failed", extra={"err": exc.__class__.__name__})
    try:
        await memory.delete_group(str(row["group_id"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph partition delete failed", extra={"err": exc.__class__.__name__})


async def _read_bounded(file: UploadFile, limit: int) -> bytes:
    """Read the upload, aborting as soon as it exceeds the limit."""
    chunks: list[bytes] = []
    size = 0
    while True:
        block = await file.read(1024 * 256)
        if not block:
            break
        size += len(block)
        if size > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"upload exceeds {limit} bytes",
            )
        chunks.append(block)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty upload")
    return b"".join(chunks)


def _safe_filename(name: str | None) -> str:
    """Strip any path component from a client-supplied filename."""
    if not name:
        return "upload.pdf"
    return name.replace("\\", "/").rsplit("/", 1)[-1][:255] or "upload.pdf"


def _uuid(value: str) -> str:
    """Validate a path parameter as a UUID."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="document_id must be a UUID"
        ) from exc
