"""Connected calendars (docs/research/UPC_INTEGRATION.md §2.2): the student pastes their Moodle/Atenea calendar
export URL once; Novi re-reads it daily and turns deadlines and exam events into assignments, exams and cards.

Deterministic only (no LLM). The URL carries a bearer token, so it is stored encrypted and never returned.
Sync is idempotent on the iCal UID, so re-syncing updates dates instead of duplicating.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import AgentTrace, ToolContext
from app.auth.crypto import SecretUnreadable, decrypt, encrypt
from app.command.parse import best_match
from app.db.base import utcnow
from app.db.models import Assignment, CalendarFeed, Course, Exam, Job
from app.onboarding import extract as _extract
from app.onboarding.extract import ExtractionError
from app.onboarding.timetable import EXAM_WORDS, ics_dt, ics_events, ics_unescape
from app.orchestrator import cards
from app.orchestrator.events import emit

SYNC_EVERY = timedelta(hours=24)
CARD_HORIZON_DAYS = 14  # new deadlines closer than this get a feed card
WINDOW = (timedelta(days=-1), timedelta(days=150))  # which events are imported
# Moodle "due"/"closes" events, in the languages UPC students see (EN/ES/CA).
_DUE = re.compile(r"\b(due|deadline|closes|close|submission|venç|venc|vence|vencimiento|lliurament|entrega|"
                  r"tanca|cierra|termini|plazo|fecha l[ií]mite|data l[ií]mit)\b", re.I)


@dataclass
class Deadline:
    uid: str
    title: str
    when: datetime | date
    course_hint: str
    is_exam: bool


def parse_deadlines(text: str, tz: str) -> tuple[list[Deadline], int]:
    """One-off dated events that look like deadlines or exams. Returns (deadlines, ignored_other)."""
    zone = ZoneInfo(tz)
    out: list[Deadline] = []
    ignored = 0
    for ev in ics_events(text):
        summary = ics_unescape(ev.get("SUMMARY", ("", {}))[0])
        if not summary or "DTSTART" not in ev:
            continue
        if "RRULE" in ev:  # weekly classes belong to the timetable import, not here
            ignored += 1
            continue
        start = ics_dt(*ev["DTSTART"], zone)
        end = ics_dt(*ev["DTEND"], zone) if "DTEND" in ev else start
        hint = " ".join(filter(None, [ics_unescape(ev.get("CATEGORIES", ("", {}))[0]),
                                      ics_unescape(ev.get("DESCRIPTION", ("", {}))[0])[:200]]))
        is_exam = bool(EXAM_WORDS.search(summary))
        is_due = bool(_DUE.search(summary)) or start == end  # Moodle due events are instants
        if not (is_exam or is_due):
            ignored += 1
            continue
        uid = ev.get("UID", ("", {}))[0] or f"{summary}|{ev['DTSTART'][0]}"
        out.append(Deadline(uid=uid[:300], title=summary[:200], when=start, course_hint=hint, is_exam=is_exam))
    return out, ignored


def masked(url: str) -> str:
    return urlparse(url).hostname or "calendar"


# ------------------------------------------------------------------ connect / sync
async def connect(db: Session, url: str, tz: str, label: str = "") -> tuple[CalendarFeed, Job, int]:
    """Validate by reading it once (SSRF-guarded), store encrypted, queue the first sync. Returns upcoming count."""
    url = url.strip().replace("webcal://", "https://", 1)
    data = await _extract.fetch_ics(url)
    text = data.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text[:2000]:
        raise ExtractionError("That link doesn't return a calendar (.ics). Copy the URL from Calendar → Export.")
    deadlines, _ = parse_deadlines(text, tz)
    for feed in db.scalars(select(CalendarFeed)):
        try:
            if decrypt(feed.url_enc) == url:
                return feed, emit(db, "calendar_sync_due", {"feed_id": feed.id}, source="manual"), len(deadlines)
        except SecretUnreadable:
            continue
    feed = CalendarFeed(url_enc=encrypt(url), host=masked(url), label=label[:120] or masked(url))
    db.add(feed)
    db.flush()
    return feed, emit(db, "calendar_sync_due", {"feed_id": feed.id}, source="manual"), len(deadlines)


async def sync(ctx: ToolContext, feed: CalendarFeed, tz: str) -> dict[str, Any]:
    trace = AgentTrace(ctx, "calendar", "deterministic", f"Refresh your {feed.label} calendar")
    try:
        url = decrypt(feed.url_enc)
        data = await _extract.fetch_ics(url)
    except (ExtractionError, SecretUnreadable) as exc:
        feed.last_error = str(exc)
        trace.step("tool", "fetch_calendar", {"host": feed.host}, {"error": str(exc)}, ok=False)
        trace.finish("failed", error=str(exc))
        cards.create_card(ctx.db, "job_failed", f"I couldn't refresh your {feed.label} calendar", body=str(exc),
                          actions=[cards.DISMISS], data={"feed_id": feed.id}, dedupe_key=f"calendar_error:{feed.id}")
        ctx.db.commit()
        return {"error": str(exc)}
    trace.step("tool", "fetch_calendar", {"host": feed.host}, {"bytes": len(data)})
    deadlines, ignored = parse_deadlines(data.decode("utf-8", errors="replace"), tz)
    now = ctx.now
    today = now.astimezone(ZoneInfo(tz)).date()
    courses = list(ctx.db.scalars(select(Course)))
    stats: dict[str, Any] = {"new": 0, "updated": 0, "exams": 0, "unmatched": 0, "ignored": ignored,
                             "unmatched_examples": []}
    for d in deadlines:
        day = d.when.date() if isinstance(d.when, datetime) else d.when
        if not (today + WINDOW[0] <= day <= today + WINDOW[1]):
            continue
        cid, _ = best_match(f"{d.course_hint} {d.title}", [(c.id, c.name) for c in courses])
        if cid is None:
            stats["unmatched"] += 1
            if len(stats["unmatched_examples"]) < 5:
                stats["unmatched_examples"].append(d.title[:80])
            continue
        course = next(c for c in courses if c.id == cid)
        if d.is_exam:
            exam = ctx.db.scalar(select(Exam).where(Exam.external_uid == d.uid))
            if exam is None:
                exam = cards.create_exam_with_followups(ctx.db, course, day, d.title[:160])
                exam.external_uid = d.uid
                stats["new"] += 1
            elif exam.exam_date != day:
                exam.exam_date, stats["updated"] = day, stats["updated"] + 1
            stats["exams"] += 1
            continue
        due_at = d.when if isinstance(d.when, datetime) else None
        a = ctx.db.scalar(select(Assignment).where(Assignment.external_uid == d.uid))
        if a is None:
            a = Assignment(course_id=course.id, title=d.title, due_date=day, due_at=due_at, external_uid=d.uid)
            ctx.db.add(a)
            ctx.db.flush()
            stats["new"] += 1
            if 0 <= (day - today).days <= CARD_HORIZON_DAYS:
                when = d.when.astimezone(ZoneInfo(tz)).strftime("%a %d %b, %H:%M") if due_at else day.strftime("%a %d %b")
                cards.create_card(
                    ctx.db, "deadline", f"{d.title} — due {when}",
                    body=f"From your {feed.label} calendar · {course.name}.",
                    actions=[cards.action("mark_done", "Mark done", primary=True),
                             cards.action("open", "Open course", "link", href=f"/subjects/{course.id}"),
                             cards.DISMISS],
                    data={"assignment_id": a.id, "course_id": course.id, "feed_id": feed.id},
                    dedupe_key=f"deadline:{d.uid}", course_id=course.id)
        elif (a.due_date, a.due_at) != (day, due_at) or a.title != d.title:
            a.due_date, a.due_at, a.title = day, due_at, d.title
            stats["updated"] += 1
    trace.step("decision", "calendar_synced", {}, {k: v for k, v in stats.items() if k != "unmatched_examples"})
    first_sync = feed.last_synced_at is None
    feed.last_synced_at, feed.last_error, feed.stats = utcnow(), "", stats
    if first_sync:  # make the connection visible: what was read, what was filed, what happens next
        filed = stats["new"]
        other = (f" {stats['unmatched']} event(s) aren't from your courses (e.g. “{stats['unmatched_examples'][0]}”), "
                 "so I left them out." if stats["unmatched"] and stats["unmatched_examples"] else "")
        cards.create_card(
            ctx.db, "calendar_connected", f"Connected to your {feed.label} calendar",
            body=(f"I read {len(deadlines)} dated event(s) and filed {filed} deadline/exam(s) from your subjects."
                  f"{other} I'll re-check it every day and turn new deadlines from your subjects into cards; "
                  "exam events become exams with Exam Pack reminders."),
            actions=[cards.action("open", "See it in Schedule", "link", primary=True, href="/schedule"), cards.DISMISS],
            data={"feed_id": feed.id}, dedupe_key=f"calendar_connected:{feed.id}", priority=46)
    cards.resolve_matching(ctx.db, ("job_failed",), feed_id=feed.id)
    summary = f"{stats['new']} new, {stats['updated']} updated" + (f", {stats['unmatched']} unmatched" if stats["unmatched"] else "")
    trace.finish("succeeded", summary)
    ctx.db.commit()
    return stats


def due_for_sync(feed: CalendarFeed, now: datetime) -> bool:
    return feed.last_synced_at is None or now - feed.last_synced_at >= SYNC_EVERY
