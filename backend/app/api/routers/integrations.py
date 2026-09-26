"""Connected calendars and UPC course guides (docs/research/UPC_INTEGRATION.md: the GO items)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_or_404
from app.api.schemas import JobOut
from app.db.engine import system_session_ctx
from app.db.models import CalendarFeed, Course, User
from app.integrations import calendar_feed, upc_guides
from app.onboarding.extract import ExtractionError
from app.orchestrator import cards

router = APIRouter(tags=["integrations"])


class FeedOut(BaseModel):
    """Never includes the URL (it carries a token)."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    host: str
    label: str
    last_synced_at: datetime | None
    last_error: str
    stats: dict[str, Any]
    created_at: datetime


class ConnectIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    label: str = Field(default="", max_length=120)


class ConnectOut(BaseModel):
    feed: FeedOut
    job: JobOut
    upcoming: int
    message: str


class GuideIn(BaseModel):
    code: str = Field(min_length=5, max_length=6)


class GuideOut(BaseModel):
    course_id: str
    code: str
    title: str
    syllabus_chars: int
    message: str


def user_tz(user_id: str) -> str:
    with system_session_ctx() as sdb:
        return sdb.get(User, user_id).timezone  # type: ignore[union-attr]


async def connect_calendar(db: DB, user_id: str, url: str, label: str = "") -> ConnectOut:
    try:
        feed, job, upcoming = await calendar_feed.connect(db, url, user_tz(user_id), label)
    except ExtractionError as exc:
        raise HTTPException(422, str(exc)) from exc
    cards.resolve_matching(db, ("connect_calendar",))
    db.flush()
    return ConnectOut(feed=FeedOut.model_validate(feed), job=JobOut.model_validate(job), upcoming=upcoming,
                      message=f"Connected {feed.label}: {upcoming} dated deadline/exam event(s) found. "
                              "I'll file them now and re-check every day.")


async def apply_guide(db: DB, course: Course, code: str) -> GuideOut:
    try:
        guide = await upc_guides.fetch_guide(code)
    except upc_guides.GuideError as exc:
        raise HTTPException(422, str(exc)) from exc
    course.syllabus = guide.syllabus
    cards.resolve_matching(db, ("syllabus_wanted",), course_id=course.id)
    return GuideOut(course_id=course.id, code=guide.code, title=guide.title, syllabus_chars=len(guide.syllabus),
                    message=f"Imported the syllabus from the course guide{f' ({guide.title})' if guide.title else ''}.")


@router.get("/calendars", response_model=list[FeedOut])
def list_calendars(db: DB) -> list[CalendarFeed]:
    return list(db.scalars(select(CalendarFeed).order_by(CalendarFeed.created_at)))


@router.post("/calendars", response_model=ConnectOut, status_code=201)
async def add_calendar(body: ConnectIn, user: CurrentUser, db: DB) -> ConnectOut:
    return await connect_calendar(db, user.id, body.url, body.label)


@router.delete("/calendars/{feed_id}", status_code=204)
def remove_calendar(feed_id: str, db: DB) -> None:
    """Stops syncing. Deadlines already imported stay (they are the student's data now)."""
    db.delete(get_or_404(db, CalendarFeed, feed_id))


@router.post("/courses/{course_id}/guide", response_model=GuideOut)
async def import_guide(course_id: str, body: GuideIn, db: DB) -> GuideOut:
    return await apply_guide(db, get_or_404(db, Course, course_id), body.code)
