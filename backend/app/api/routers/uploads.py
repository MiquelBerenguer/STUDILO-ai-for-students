from __future__ import annotations

import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_or_404
from app.api.schemas import ClassSessionOut, IngestionLogOut, UploadDetailOut, UploadOut
from app.config.settings import get_settings
from app.db.base import new_id
from app.db.models import ClassSession, Course, IngestionLog, Job, Upload
from app.ingestion.detect import detect_type
from app.orchestrator.events import emit
from app.orchestrator.state_machines import JOB, UPLOAD, transition
from app.tools.store import upload_path

router = APIRouter(tags=["uploads"])

_EXT = {"pdf": ".pdf", "png": ".png", "jpeg": ".jpg", "heic": ".heic", "webp": ".webp", "tiff": ".tiff",
        "text": ".txt"}


@router.post("/uploads", response_model=list[UploadOut], status_code=201)
async def create_uploads(
    user: CurrentUser, db: DB,
    files: Annotated[list[UploadFile], File(description="PDF, photos (JPG/PNG/HEIC) or .txt/.md")],
    course_id: Annotated[str, Form()],
    class_session_id: Annotated[str | None, Form()] = None,
    kind: Annotated[Literal["notes", "past_exam"], Form()] = "notes",
) -> list[Upload]:
    get_or_404(db, Course, course_id)
    if class_session_id:
        session = get_or_404(db, ClassSession, class_session_id)
        if session.course_id != course_id:
            raise HTTPException(422, "That class session belongs to another subject")
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    out: list[Upload] = []
    for f in files:
        data = await f.read()
        if not data:
            raise HTTPException(422, f"{f.filename} is empty")
        if len(data) > max_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                f"{f.filename} is larger than {settings.MAX_UPLOAD_MB} MB")
        ftype = detect_type(data)
        if ftype == "unsupported":
            raise HTTPException(415, f"{f.filename}: unsupported file type. Use PDF, JPG, PNG, HEIC or text.")
        upload_id = new_id()
        rel = f"uploads/{user.id}/{upload_id}{_EXT[ftype]}"
        path = settings.data_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        upload = Upload(id=upload_id, course_id=course_id, class_session_id=class_session_id, kind=kind,
                        filename=(f.filename or "upload")[:255], detected_type=ftype, storage_path=rel,
                        sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                        status_message="Queued")
        db.add(upload)
        db.flush()
        job = emit(db, "upload_completed", {"upload_id": upload.id}, source="manual")
        upload.job_id = job.id
        out.append(upload)
    return out


@router.get("/uploads", response_model=list[UploadOut])
def list_uploads(db: DB, course_id: str | None = None, limit: int = 50) -> list[Upload]:
    q = select(Upload).order_by(Upload.created_at.desc()).limit(min(limit, 200))
    if course_id:
        q = q.where(Upload.course_id == course_id)
    return list(db.scalars(q))


@router.get("/uploads/{upload_id}", response_model=UploadDetailOut)
def get_upload(upload_id: str, db: DB) -> UploadDetailOut:
    upload = get_or_404(db, Upload, upload_id)
    logs = list(db.scalars(select(IngestionLog).where(IngestionLog.upload_id == upload.id)
                           .order_by(IngestionLog.created_at)))
    return UploadDetailOut.model_validate({**UploadOut.model_validate(upload).model_dump(),
                                           "extracted_md": upload.extracted_md,
                                           "log": [IngestionLogOut.model_validate(r) for r in logs]})


_MEDIA = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg", "heic": "image/heic",
          "webp": "image/webp", "tiff": "image/tiff", "text": "text/plain; charset=utf-8"}


@router.get("/uploads/{upload_id}/file")
def get_upload_file(upload_id: str, db: DB) -> FileResponse:
    """Serve with the media type from the magic-byte detection, never from the user-supplied filename."""
    upload = get_or_404(db, Upload, upload_id)
    return FileResponse(upload_path(upload), media_type=_MEDIA.get(upload.detected_type, "application/octet-stream"),
                        filename=upload.filename, content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"})


@router.post("/uploads/{upload_id}/retry", response_model=UploadOut)
def retry_upload(upload_id: str, db: DB) -> Upload:
    upload = get_or_404(db, Upload, upload_id)
    if upload.state != "failed":
        raise HTTPException(409, "Only failed uploads can be retried")
    transition(UPLOAD, upload, "received")
    upload.error, upload.status_message = "", "Queued (retry)"
    job = db.get(Job, upload.job_id) if upload.job_id else None
    if job is not None and job.state == "failed":
        transition(JOB, job, "queued")
        job.error = ""
    else:
        upload.job_id = emit(db, "upload_completed", {"upload_id": upload.id}, source="manual").id
    return upload


@router.get("/sessions", response_model=list[ClassSessionOut])
def list_sessions(db: DB, course_id: str | None = None, state: str | None = None, limit: int = 60) -> list[ClassSession]:
    q = select(ClassSession).order_by(ClassSession.session_date.desc()).limit(min(limit, 300))
    if course_id:
        q = q.where(ClassSession.course_id == course_id)
    if state:
        q = q.where(ClassSession.state == state)
    return list(db.scalars(q))
