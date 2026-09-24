"""User-scoped domain operations shared by tools, routes and fallbacks.

Every function takes a user-scoped session (app.db.engine), so reads are filtered by user_id at the
session level and writes are stamped with it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import vectors
from app.agents.base import ToolError
from app.config.settings import get_settings
from app.db.models import Chunk, Course, NoteSection, SectionSource, Topic, Upload
from app.ingestion.chunker import split_text
from app.llm.embeddings import embed_texts


def upload_path(upload: Upload) -> Path:
    return get_settings().data_dir / upload.storage_path


def read_upload_bytes(upload: Upload) -> bytes:
    return upload_path(upload).read_bytes()


def must_get(db: Session, model: type, obj_id: str | None, label: str | None = None):  # type: ignore[no-untyped-def]
    """Scoped lookup for tools: unknown or foreign ids produce the same model-visible error."""
    obj = db.get(model, obj_id) if obj_id else None
    if obj is None:
        raise ToolError(f"{label or model.__name__} {obj_id!r} not found")
    return obj


def to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


# ------------------------------------------------------------------ topics & sections
def create_topic(db: Session, course_id: str, title: str, summary: str = "", parent_id: str | None = None) -> Topic:
    must_get(db, Course, course_id, "course")
    if parent_id:
        parent = must_get(db, Topic, parent_id, "parent topic")
        if parent.course_id != course_id:
            raise ToolError("parent topic belongs to another subject")
    pos = (db.scalar(select(func.max(Topic.position)).where(Topic.course_id == course_id)) or 0) + 1
    topic = Topic(course_id=course_id, title=title.strip()[:160], summary=summary.strip(), parent_id=parent_id,
                  position=pos)
    db.add(topic)
    db.flush()
    return topic


def link_source(db: Session, section: NoteSection, upload_id: str) -> None:
    upload = must_get(db, Upload, upload_id, "upload")
    if upload.course_id != section.course_id:
        raise ToolError("upload belongs to another subject")
    exists = db.scalar(select(SectionSource).where(SectionSource.section_id == section.id,
                                                   SectionSource.upload_id == upload_id))
    if exists is None:
        db.add(SectionSource(section_id=section.id, upload_id=upload_id))
        db.flush()


def append_section(db: Session, topic: Topic, heading: str, content_md: str, source_upload_ids: list[str],
                   after_section_id: str | None = None) -> NoteSection:
    if not source_upload_ids:
        raise ToolError("every section must cite at least one source upload")
    sections = list(db.scalars(select(NoteSection).where(NoteSection.topic_id == topic.id)
                               .order_by(NoteSection.position)))
    if after_section_id:
        anchor = next((s for s in sections if s.id == after_section_id), None)
        if anchor is None:
            raise ToolError(f"section {after_section_id!r} is not in this topic")
        pos = anchor.position + 1
        for s in sections:
            if s.position >= pos:
                s.position += 1
    else:
        pos = (sections[-1].position + 1) if sections else 0
    section = NoteSection(course_id=topic.course_id, topic_id=topic.id, position=pos, heading=heading.strip()[:200],
                          content_md=content_md.strip())
    db.add(section)
    db.flush()
    for uid in source_upload_ids:
        link_source(db, section, uid)
    return section


def revise_section(db: Session, section: NoteSection, content_md: str, source_upload_ids: list[str],
                   heading: str | None = None) -> NoteSection:
    if not source_upload_ids:
        raise ToolError("a revision must cite the upload(s) it comes from")
    section.content_md = content_md.strip()
    if heading:
        section.heading = heading.strip()[:200]
    section.version += 1
    for uid in source_upload_ids:
        link_source(db, section, uid)
    db.flush()
    return section


async def reindex_section(db: Session, user_id: str, section: NoteSection) -> int:
    """Re-chunk and re-embed one section into the user's partition of the vector store."""
    old = list(db.scalars(select(Chunk).where(Chunk.section_id == section.id)))
    for dim in {c.embedding_dim for c in old}:
        vectors.delete(db, [c.id for c in old if c.embedding_dim == dim], dim)
    db.execute(delete(Chunk).where(Chunk.section_id == section.id))
    pieces = split_text(f"{section.heading}\n\n{section.content_md}")
    if not pieces:
        return 0
    db.commit()  # release the write lock before a potentially slow embedding call
    vecs, _label = await embed_texts(pieces, user_id)
    for i, (text, vec) in enumerate(zip(pieces, vecs, strict=True)):
        chunk = Chunk(course_id=section.course_id, topic_id=section.topic_id, section_id=section.id, idx=i, text=text,
                      embedding_dim=len(vec))
        db.add(chunk)
        db.flush()
        vectors.upsert(db, user_id, chunk.id, vec)
    return len(pieces)


async def search_notes(db: Session, user_id: str, query: str, course_id: str | None = None,
                       topic_id: str | None = None, k: int = 6) -> list[dict[str, object]]:
    vecs, _ = await embed_texts([query], user_id)
    hits = vectors.knn(db, user_id, vecs[0], k=max(k * 4, 20))
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for chunk_id, dist in hits:
        chunk = db.get(Chunk, chunk_id)  # scoped: a foreign chunk id would return None
        if chunk is None or (course_id and chunk.course_id != course_id) or (topic_id and chunk.topic_id != topic_id):
            continue
        if chunk.section_id in seen:
            continue
        seen.add(chunk.section_id)
        section = db.get(NoteSection, chunk.section_id)
        topic = db.get(Topic, chunk.topic_id)
        if section is None or topic is None:
            continue
        out.append({"section_id": section.id, "topic_id": topic.id, "topic_title": topic.title,
                    "heading": section.heading, "snippet": chunk.text[:700], "score": round(1 - dist, 3)})
        if len(out) >= k:
            break
    return out


def section_sources(db: Session, section_ids: list[str]) -> dict[str, list[Upload]]:
    if not section_ids:
        return {}
    rows = db.execute(select(SectionSource.section_id, Upload).join(Upload, Upload.id == SectionSource.upload_id)
                      .where(SectionSource.section_id.in_(section_ids))).all()
    out: dict[str, list[Upload]] = {}
    for sid, upload in rows:
        out.setdefault(sid, []).append(upload)
    return out


def topic_sections(db: Session, topic_id: str) -> list[NoteSection]:
    return list(db.scalars(select(NoteSection).where(NoteSection.topic_id == topic_id).order_by(NoteSection.position)))
