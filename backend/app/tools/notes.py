"""Notes agent tools. Incremental only: there is no 'replace the whole note' operation (DECISIONS D-14)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.agents.base import Tool, ToolContext, ToolError
from app.db.models import NoteSection, Topic
from app.tools import store


def _course(ctx: ToolContext) -> str:
    return ctx.state["course_id"]


def _topic(ctx: ToolContext, topic_id: str) -> Topic:
    topic = store.must_get(ctx.db, Topic, topic_id, "topic")
    if topic.course_id != _course(ctx):
        raise ToolError("that topic belongs to another subject")
    return topic


class SearchArgs(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    topic_id: str | None = None
    k: int = Field(default=5, ge=1, le=10)


class TopicArg(BaseModel):
    topic_id: str


class UpdateArgs(BaseModel):
    topic_id: str
    operation: Literal["append_section", "revise_section"]
    content_md: str = Field(min_length=1, max_length=20000,
                            description="Markdown with LaTeX math ($...$ inline, $$...$$ display)")
    source_upload_ids: list[str] = Field(min_length=1, description="uploads this content comes from")
    heading: str | None = Field(default=None, max_length=200, description="required for append_section")
    section_id: str | None = Field(default=None, description="required for revise_section")
    after_section_id: str | None = Field(default=None, description="append after this section (default: end)")


class CreateTopicArgs(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    summary: str = Field(default="", max_length=600)
    parent_topic_id: str | None = None


class LinkArgs(BaseModel):
    section_id: str
    upload_id: str


class FinishArgs(BaseModel):
    summary: str = Field(max_length=2000, description="one paragraph: what was added or changed, per topic")


async def search_notes_tool(ctx: ToolContext, a: SearchArgs) -> list[dict[str, object]]:
    if a.topic_id:
        _topic(ctx, a.topic_id)
    ctx.db.commit()
    return await store.search_notes(ctx.db, ctx.user_id, a.query, course_id=_course(ctx), topic_id=a.topic_id, k=a.k)


def get_topic_note_tool(ctx: ToolContext, a: TopicArg) -> dict[str, object]:
    topic = _topic(ctx, a.topic_id)
    sections = store.topic_sections(ctx.db, topic.id)
    sources = store.section_sources(ctx.db, [s.id for s in sections])
    return {"topic_id": topic.id, "title": topic.title, "summary": topic.summary, "sections": [
        {"section_id": s.id, "position": s.position, "heading": s.heading, "content_md": s.content_md[:4000],
         "sources": [u.filename for u in sources.get(s.id, [])]} for s in sections]}


async def update_topic_note_tool(ctx: ToolContext, a: UpdateArgs) -> dict[str, object]:
    topic = _topic(ctx, a.topic_id)
    if a.operation == "append_section":
        if not a.heading:
            raise ToolError("append_section requires a heading")
        section = store.append_section(ctx.db, topic, a.heading, a.content_md, a.source_upload_ids, a.after_section_id)
        store.fx(ctx.state)["created_sections"].append(section.id)
    else:
        section = store.must_get(ctx.db, NoteSection, a.section_id, "section")
        if section.topic_id != topic.id:
            raise ToolError("section is not in that topic")
        revised = store.fx(ctx.state)["revised"]
        created_here = section.id in store.fx(ctx.state)["created_sections"]
        if not created_here and section.id not in revised:
            revised[section.id] = {"heading": section.heading, "content_md": section.content_md,
                                   "before_version": section.version}
        store.revise_section(ctx.db, section, a.content_md, a.source_upload_ids, a.heading)
        if created_here:
            section.version = 1  # still this run's own new section: undo deletes it
        else:
            revised[section.id]["after_version"] = section.version
    chunks = await store.reindex_section(ctx.db, ctx.user_id, section)
    ctx.state.setdefault("touched_topics", set()).add(topic.id)
    ctx.state.setdefault("touched_sections", set()).add(section.id)
    return {"section_id": section.id, "version": section.version, "indexed_chunks": chunks}


def create_topic_tool(ctx: ToolContext, a: CreateTopicArgs) -> dict[str, object]:
    existing = ctx.db.scalar(select(Topic).where(Topic.course_id == _course(ctx), Topic.title == a.title.strip()))
    if existing:
        return {"topic_id": existing.id, "title": existing.title, "note": "topic already existed"}
    topic = store.create_topic(ctx.db, _course(ctx), a.title, a.summary, a.parent_topic_id)
    store.fx(ctx.state)["created_topics"].append(topic.id)
    return {"topic_id": topic.id, "title": topic.title}


def link_source_tool(ctx: ToolContext, a: LinkArgs) -> dict[str, object]:
    section = store.must_get(ctx.db, NoteSection, a.section_id, "section")
    if section.course_id != _course(ctx):
        raise ToolError("section belongs to another subject")
    store.link_source(ctx.db, section, a.upload_id)
    return {"ok": True}


def finish_tool(ctx: ToolContext, a: FinishArgs) -> dict[str, object]:
    if not ctx.state.get("touched_sections"):
        raise ToolError("no section was added or revised yet; merge the new notes first")
    return {"summary": a.summary, "topics": sorted(ctx.state["touched_topics"]),
            "sections": sorted(ctx.state["touched_sections"])}


def notes_tools() -> list[Tool]:
    return [
        Tool("search_notes", "Semantic search over this subject's notes.", SearchArgs, search_notes_tool),
        Tool("get_topic_note", "Read a topic's note: sections with ids, headings, content, sources.", TopicArg,
             get_topic_note_tool),
        Tool("update_topic_note", "Append a new section, or revise ONE existing section. Always cite source uploads.",
             UpdateArgs, update_topic_note_tool),
        Tool("create_topic", "Create a topic in this subject (only if the notes clearly cover a separate topic).",
             CreateTopicArgs, create_topic_tool),
        Tool("link_source", "Link an existing section to an upload it is based on.", LinkArgs, link_source_tool),
        Tool("finish", "Finish after merging. Summarise what changed.", FinishArgs, finish_tool, terminal=True),
    ]
