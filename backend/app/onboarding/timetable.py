"""Deterministic timetable parsing (onboarding, UX.md §8). Pure functions, no I/O, no LLM.

Three parsers, all producing the same typed `SlotOut` list:
- `parse_grid`: positioned text tokens (PDF text layer or OCR boxes) + an optional colour image. Finds the
  weekday header row → columns, the time labels → a y→time mapping, then cells (coloured blocks when
  present, otherwise vertical text clusters) → slots. Reports a confidence; the pipeline escalates to the
  vision model when it is low.
- `parse_ics`: iCalendar (RRULE weekly events, repeated events, exam-like events → exam dates).
- `parse_text`: pasted text, one class per line ("Mon 9:00-11:00 Thermodynamics, Room A2, Prof. García").
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator

LOW_CONFIDENCE = 0.8  # fields below this are highlighted in the confirm step
GRID_ACCEPT = 0.75  # below this the grid result is not trusted → vision / LLM

# ------------------------------------------------------------------ typed output (JEV-style validation)
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class SlotOut(BaseModel):
    subject: str = Field(min_length=1, max_length=120)
    weekday: int = Field(ge=0, le=6)  # 0 = Monday
    start: str
    end: str
    room: str = Field(default="", max_length=120)
    professor: str = Field(default="", max_length=160)
    confidence: dict[str, float] = Field(default_factory=lambda: {"subject": 1.0, "time": 1.0, "room": 1.0,
                                                                  "professor": 1.0})

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        v = v.strip()
        if re.fullmatch(r"\d:\d\d", v):
            v = "0" + v
        if not _HHMM.match(v):
            raise ValueError(f"time must be HH:MM, got {v!r}")
        return v

    @model_validator(mode="after")
    def _order(self) -> SlotOut:
        mins = _mins(self.end) - _mins(self.start)
        if not 15 <= mins <= 6 * 60:
            raise ValueError(f"class must last 15 min – 6 h, got {self.start}–{self.end}")
        self.subject = " ".join(self.subject.split())
        return self


class ExamOut(BaseModel):
    subject: str
    title: str
    date: date


class Extraction(BaseModel):
    slots: list[SlotOut]
    exams: list[ExamOut] = Field(default_factory=list)
    method: Literal["ics", "grid", "text", "vision", "llm_text", "none"]
    confidence: float
    warnings: list[str] = Field(default_factory=list)
    run_id: str | None = None


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(mins: float) -> str:
    mins = int(round(mins))
    return f"{mins // 60:02d}:{mins % 60:02d}"


def norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


DAY_WORDS: dict[str, int] = {}
for _i, _names in enumerate([
    "monday mon lunes lun dilluns dl", "tuesday tue tues martes mar dimarts dt",
    "wednesday wed miercoles mie mier dimecres dc", "thursday thu thur thurs jueves jue dijous dj",
    "friday fri viernes vie divendres dv", "saturday sat sabado sab dissabte ds", "sunday sun domingo dom diumenge dg",
]):
    for _w in _names.split():
        DAY_WORDS[_w] = _i


def weekday_of(word: str) -> int | None:
    w = re.sub(r"[^a-z]", "", norm(word).split(" ")[0] if word.strip() else "")
    return DAY_WORDS.get(w)


_TIME = re.compile(r"\b([01]?\d|2[0-3])\s*[:.h]\s*([0-5]\d)\b")
_TIME_RANGE = re.compile(r"\b([01]?\d|2[0-3])(?:\s*[:.h]\s*([0-5]\d))?\s*(?:-|–|—|to|a|fins)\s*"
                         r"([01]?\d|2[0-3])(?:\s*[:.h]\s*([0-5]\d))?\b(?!\s*/)")
_ROOM_KW = re.compile(r"\b(aula|room|sala|lab|laboratori|laboratorio|classroom|edifici|edificio|building|aulari)\b",
                      re.I)
_ROOM_LINE = re.compile(r"^(aula|room|sala|lab|laboratori\w*|classroom|edifici\w*|building|aulari)\b\.?\s*[\w\-/. ]*\d",
                        re.I)  # "Aula A2-101", "Lab C4-005" (keyword first, then a code with a digit)
_ROOM_CODE = re.compile(r"\b[A-Z]{1,3}\d{0,2}[-\s.]?\d{2,3}[A-Z]?\b")
_PROF_KW = re.compile(r"\b(prof|profa|professor|professora|dr|dra|docent|teacher)\b\.?\s*", re.I)


def split_cell(lines: list[str]) -> tuple[str, str, str, float, float]:
    """Cell lines → (subject, room, professor, room_conf, prof_conf)."""
    subject_parts: list[str] = []
    room = prof = ""
    room_conf = prof_conf = 1.0
    for line in lines:
        line = line.strip(" ,;·|")
        if not line:
            continue
        if _PROF_KW.search(line):
            prof, prof_conf = _PROF_KW.sub("", line, count=1).strip(" .,-()"), 0.9
        elif _ROOM_LINE.search(line) or (subject_parts and _ROOM_KW.search(line) and re.search(r"\d", line)):
            room, room_conf = line, 0.9
        elif not subject_parts:
            # "Thermodynamics (A2-101)" / "Thermodynamics - García"
            m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", line)
            if m and _ROOM_CODE.search(m.group(2)):
                subject_parts.append(m.group(1))
                room, room_conf = m.group(2), 0.75
            else:
                subject_parts.append(line)
        elif _ROOM_CODE.fullmatch(line.strip()) and not room:
            room, room_conf = line.strip(), 0.7
        elif line.startswith("(") and line.endswith(")") and not prof:
            prof, prof_conf = line.strip("()"), 0.6  # "(García)" under the subject: probably the professor
        elif not room and not prof:
            subject_parts.append(line)  # wrapped subject name
    return " ".join(subject_parts).strip(), room, prof, room_conf, prof_conf


def dedupe(slots: list[SlotOut]) -> list[SlotOut]:
    seen: set[tuple[str, int, str, str]] = set()
    out = []
    for s in slots:
        key = (norm(s.subject), s.weekday, s.start, s.end)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return sorted(out, key=lambda s: (s.weekday, s.start))


def overlaps(slots: list[SlotOut]) -> list[tuple[SlotOut, SlotOut]]:
    out = []
    for i, a in enumerate(slots):
        for b in slots[i + 1:]:
            if a.weekday == b.weekday and _mins(a.start) < _mins(b.end) and _mins(b.start) < _mins(a.end):
                out.append((a, b))
    return out


# ------------------------------------------------------------------ grid parser
@dataclass
class Token:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 1.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> float:
        return self.y1 - self.y0


@dataclass
class GridResult:
    slots: list[SlotOut]
    confidence: float
    reason: str
    stats: dict[str, float | int | str]


def _cluster_rows(tokens: list[Token], tol: float) -> list[list[Token]]:
    rows: list[list[Token]] = []
    for t in sorted(tokens, key=lambda t: t.cy):
        if rows and abs(rows[-1][-1].cy - t.cy) <= tol:
            rows[-1].append(t)
        else:
            rows.append([t])
    return rows


def _lines(tokens: list[Token], tol: float) -> list[str]:
    return [" ".join(t.text for t in sorted(row, key=lambda t: t.x0)) for row in _cluster_rows(tokens, tol)]


def _interp(points: list[tuple[float, float]], y: float) -> float:
    """Piecewise-linear y → minutes, extrapolating with the nearest segment."""
    if len(points) == 1:
        return points[0][1]
    for (ya, ta), (yb, tb) in zip(points, points[1:], strict=False):
        if y <= yb or (yb, tb) == points[-1]:
            return ta + (tb - ta) * (y - ya) / (yb - ya) if yb != ya else ta
    return points[-1][1]


def _colored_blocks(img: np.ndarray, x_min: float, y_min: float, min_w: float, min_h: float) -> list[tuple[int, int, int, int]]:
    import cv2

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 1] > 28) & (hsv[:, :, 2] > 70)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w >= min_w and h >= min_h and x + w / 2 > x_min and y + h / 2 > y_min:
            fill = cv2.contourArea(c) / float(w * h)
            if fill > 0.6:  # solid blocks, not text strokes or lines
                rects.append((x, y, w, h))
    return rects


def parse_grid(tokens: list[Token], img: np.ndarray | None = None) -> GridResult:
    tokens = [t for t in tokens if t.text.strip()]
    if len(tokens) < 6:
        return GridResult([], 0.0, "too little text to be a timetable grid", {"tokens": len(tokens)})
    med_h = statistics.median(t.h for t in tokens) or 10.0
    # 1) weekday header row
    day_tokens = [t for t in tokens if weekday_of(t.text) is not None and len(norm(t.text)) <= 24]
    best: list[Token] = []
    for row in _cluster_rows(day_tokens, med_h * 0.8):
        by_day: dict[int, Token] = {}
        for t in row:
            by_day.setdefault(weekday_of(t.text), t)  # type: ignore[arg-type]
        if len(by_day) > len(best):
            best = sorted(by_day.values(), key=lambda t: t.cx)
    if len(best) < 2:
        return GridResult([], 0.0, "no row of weekday headers found", {"tokens": len(tokens)})
    days = [weekday_of(t.text) for t in best]
    if days != sorted(days):
        return GridResult([], 0.1, "weekday headers are not in order (rotated or distorted image?)", {})
    centers = [t.cx for t in best]
    gaps = [b - a for a, b in zip(centers, centers[1:], strict=False)]
    col_w = statistics.median(gaps) if gaps else (best[0].x1 - best[0].x0) * 3
    bounds = [centers[0] - col_w / 2] + [(a + b) / 2 for a, b in zip(centers, centers[1:], strict=False)] + [centers[-1] + col_w / 2]
    header_bottom = max(t.y1 for t in best)
    # 2) time labels (left of the first column, below the header)
    labels: list[tuple[float, float]] = []
    for row in _cluster_rows([t for t in tokens if t.cx < bounds[0] and t.cy > header_bottom - med_h * 0.3], med_h * 0.6):
        times = [int(m.group(1)) * 60 + int(m.group(2)) for t in row for m in [_TIME.search(t.text)] if m]
        if times:
            labels.append((statistics.mean(t.cy for t in row), float(min(times))))
    labels = sorted(set(labels))
    if len(labels) < 2 or any(b[1] <= a[1] for a, b in zip(labels, labels[1:], strict=False)):
        return GridResult([], 0.1, "no increasing column of time labels found", {"days": len(best), "labels": len(labels)})
    row_h = statistics.median(b[0] - a[0] for a, b in zip(labels, labels[1:], strict=False))
    step = statistics.median(b[1] - a[1] for a, b in zip(labels, labels[1:], strict=False))
    top_points = labels
    mids = [(y - row_h / 2, t) for y, t in labels]  # labels centred in their row: the row starts half a row above

    grid_tokens = [t for t in tokens if bounds[0] < t.cx < bounds[-1] and t.cy > header_bottom + med_h * 0.3
                   and t not in best]

    def column(x: float) -> int | None:
        for i in range(len(best)):
            if bounds[i] <= x < bounds[i + 1]:
                return i
        return None

    # 3) cells: coloured blocks if the image has them, else vertical text clusters
    cells: list[tuple[int, float, float, list[Token]]] = []
    blocks = _colored_blocks(img, bounds[0], header_bottom, col_w * 0.45, row_h * 0.4) if img is not None else []
    used: set[int] = set()
    for x, y, w, h in blocks:
        col = column(x + w / 2)
        inside = [t for t in grid_tokens if x <= t.cx <= x + w and y <= t.cy <= y + h]
        if col is None or not inside:
            continue
        used.update(id(t) for t in inside)
        cells.append((col, float(y), float(y + h), inside))
    method = "blocks" if cells else "clusters"
    if not cells:
        for col in range(len(best)):
            col_tokens = sorted((t for t in grid_tokens if column(t.cx) == col), key=lambda t: t.cy)
            group: list[Token] = []
            for t in col_tokens:
                if group and t.y0 - group[-1].y1 > med_h * 1.3:
                    cells.append((col, group[0].y0, group[-1].y1, group))
                    group = []
                group.append(t)
            if group:
                cells.append((col, group[0].y0, group[-1].y1, group))
        used = {id(t) for c in cells for t in c[3]}
    # choose how labels align with rows: block tops sit on label lines ("top") or between them ("centre")
    if method == "blocks":
        d_top = sum(min(abs(c[1] - y) for y, _ in top_points) for c in cells)
        d_mid = sum(min(abs(c[1] - y) for y, _ in mids) for c in cells)
        points = top_points if d_top <= d_mid else mids
    else:
        points = mids
    snap = 15
    slots: list[SlotOut] = []
    for col, y0, y1, toks in cells:
        if method == "clusters":  # text only tells us which rows the cell touches
            r0 = max((i for i, (y, _) in enumerate(points) if y <= y0 + med_h * 0.2), default=0)
            r1 = max((i for i, (y, _) in enumerate(points) if y <= y1 - med_h * 0.2), default=0)
            start_m, end_m = points[r0][1], points[r1][1] + step
            t_conf = 0.7
        else:
            raw_s, raw_e = _interp(points, y0), _interp(points, y1)
            start_m, end_m = round(raw_s / snap) * snap, round(raw_e / snap) * snap
            resid = max(abs(raw_s - start_m), abs(raw_e - end_m))
            t_conf = 0.95 if resid <= 5 else 0.7
        subject, room, prof, rc, pc = split_cell(_lines(toks, med_h * 0.6))
        if not subject:
            continue
        s_conf = round(min(t.conf for t in toks), 2)
        try:
            slots.append(SlotOut(subject=subject, weekday=days[col], start=_hhmm(start_m), end=_hhmm(end_m),
                                 room=room, professor=prof,
                                 confidence={"subject": s_conf, "time": t_conf, "room": rc if room else 1.0,
                                             "professor": pc if prof else 1.0}))
        except ValueError:
            continue
    slots = dedupe(slots)
    used_ratio = len(used) / max(1, len(grid_tokens))
    clash = overlaps(slots)
    confidence = round(0.5 * min(1.0, used_ratio) + 0.25 * (len(best) >= 3) + 0.25 * (len(labels) >= 3)
                       - 0.2 * bool(clash) - (0.3 if method == "clusters" else 0.0)
                       - 0.4 * (1 - len(slots) / max(1, len(cells))), 2)  # cells we could not read
    if not slots:
        confidence = 0.0
    reason = (f"{len(slots)} classes from {len(best)} day columns and {len(labels)} time rows ({method})"
              + (f"; {len(clash)} overlapping" if clash else ""))
    return GridResult(slots, max(0.0, confidence), reason,
                      {"days": len(best), "labels": len(labels), "cells": len(cells), "method": method,
                       "used_ratio": round(used_ratio, 2), "overlaps": len(clash)})


# ------------------------------------------------------------------ pasted text
def parse_text(text: str) -> list[SlotOut]:
    slots: list[SlotOut] = []
    current_days: list[int] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        words = re.split(r"[\s,/&+]+|\band\b|\by\b|\bi\b", line)
        days = []
        for w in words[:4]:
            d = weekday_of(w)
            if d is not None and d not in days:
                days.append(d)
        m = _TIME_RANGE.search(norm(line))
        if days and not m:
            current_days = days  # a day header ("Monday:") followed by lines with times
            continue
        if not m:
            continue
        days = days or current_days
        if not days:
            continue
        sh, sm, eh, em = m.group(1), m.group(2) or "00", m.group(3), m.group(4) or "00"
        rest = line[:m.start()] + " " + line[m.end():]
        for w in words[:4]:
            if weekday_of(w) is not None:
                rest = re.sub(rf"\b{re.escape(w)}\b[:,]?", " ", rest, count=1)
        parts = [p.strip() for p in re.split(r"\s*[,;|·]\s*|\s+-\s+|\t", rest) if p.strip(" :-")]
        subject, room, prof, rc, pc = split_cell(parts)
        if not subject:
            continue
        for d in days:
            try:
                slots.append(SlotOut(subject=subject.strip(" :-"), weekday=d, start=f"{int(sh):02d}:{sm}",
                                     end=f"{int(eh):02d}:{em}", room=room, professor=prof,
                                     confidence={"subject": 0.9, "time": 1.0, "room": rc if room else 1.0,
                                                 "professor": pc if prof else 1.0}))
            except ValueError:
                continue
    return dedupe(slots)


# ------------------------------------------------------------------ iCalendar
EXAM_WORDS = re.compile(r"\b(exam|examen|final|midterm|parcial|prova|test)\b", re.I)
_BYDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def ics_unfold(text: str) -> list[str]:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def ics_dt(value: str, params: dict[str, str], tz: ZoneInfo) -> datetime | date:
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").date()
    dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    if value.endswith("Z"):
        return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    if "TZID" in params:
        try:
            return dt.replace(tzinfo=ZoneInfo(params["TZID"])).astimezone(tz)
        except (KeyError, ValueError):
            return dt.replace(tzinfo=tz)
    return dt.replace(tzinfo=tz)


def ics_unescape(v: str) -> str:
    return v.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").strip()


IcsEvent = dict[str, tuple[str, dict[str, str]]]  # PROPERTY -> (value, params)


def ics_events(text: str) -> list[IcsEvent]:
    """VEVENT blocks as {PROPERTY: (value, params)} (unfolded lines; last occurrence of a property wins)."""
    events: list[IcsEvent] = []
    cur: IcsEvent | None = None
    for line in ics_unfold(text):
        line = line.rstrip("\r")
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *raw_params = head.split(";")
            params = dict(p.split("=", 1) for p in raw_params if "=" in p)
            cur[name.upper()] = (value, params)
    return events


def parse_ics(text: str, tz_name: str) -> tuple[list[SlotOut], list[ExamOut], list[str]]:
    tz = ZoneInfo(tz_name)
    events = ics_events(text)
    slots: list[SlotOut] = []
    exams: list[ExamOut] = []
    single: dict[tuple[str, int, str, str], list[tuple[str, str]]] = {}
    warnings: list[str] = []
    for ev in events:
        summary = ics_unescape(ev.get("SUMMARY", ("", {}))[0])
        if not summary or "DTSTART" not in ev:
            continue
        start = ics_dt(*ev["DTSTART"], tz)
        if not isinstance(start, datetime):
            if EXAM_WORDS.search(summary):
                exams.append(ExamOut(subject=EXAM_WORDS.sub("", summary).strip(" -:·") or summary, title=summary,
                                     date=start))
            continue
        end = ics_dt(*ev["DTEND"], tz) if "DTEND" in ev else start + timedelta(hours=1)
        if not isinstance(end, datetime):
            end = start + timedelta(hours=1)
        room = ics_unescape(ev.get("LOCATION", ("", {}))[0])
        desc = ics_unescape(ev.get("DESCRIPTION", ("", {}))[0])
        prof_m = _PROF_KW.search(desc)
        prof = re.split(r"[,;\n]", desc[prof_m.end():])[0].strip() if prof_m else ""
        rrule = ev.get("RRULE", ("", {}))[0]
        if EXAM_WORDS.search(summary) and not rrule:
            exams.append(ExamOut(subject=EXAM_WORDS.sub("", summary).strip(" -:·") or summary, title=summary,
                                 date=start.date()))
            continue
        s_hm, e_hm = start.strftime("%H:%M"), end.strftime("%H:%M")
        if "FREQ=WEEKLY" in rrule:
            byday = re.search(r"BYDAY=([A-Z,]+)", rrule)
            days = [_BYDAY[d[-2:]] for d in byday.group(1).split(",")] if byday else [start.weekday()]
            for d in days:
                slots.append(SlotOut(subject=summary, weekday=d, start=s_hm, end=e_hm, room=room, professor=prof))
        else:
            single.setdefault((summary, start.weekday(), s_hm, e_hm), []).append((room, prof))
    for (summary, wd, s_hm, e_hm), occ in single.items():
        if len(occ) >= 2:  # repeated one-off events (many campus exports) = a weekly class
            slots.append(SlotOut(subject=summary, weekday=wd, start=s_hm, end=e_hm, room=occ[0][0], professor=occ[0][1]))
    ignored = sum(1 for occ in single.values() if len(occ) < 2)
    if ignored:
        warnings.append(f"Ignored {ignored} one-off event(s) that don't repeat weekly.")
    return dedupe(slots), exams, warnings


def weekday_date(weekday: int, today: date) -> date:
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def slot_time(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))
