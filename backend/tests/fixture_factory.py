"""Deterministic generators for ingestion fixtures (no binary blobs to maintain)."""

from __future__ import annotations

import io
from datetime import date, timedelta

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

PROSE = [
    "First law of thermodynamics",
    "The first law states that energy is conserved in a closed system.",
    "Heat added to the system equals the change in internal energy",
    "plus the work done by the system on its surroundings.",
    "We studied closed systems and the sign convention for heat and work.",
    "The professor solved an example with a piston and a gas at constant pressure.",
]
EQUATIONS = ["dU = dQ - dW", "W = ∫ p dV = p (V2 - V1)", "Q = m c ΔT", "η = 1 - T_c / T_h",
             "s2 - s1 = c_p ln(T2/T1) - R ln(p2/p1)", "Δh = q - w"]


def render_lines(lines: list[str], size: int = 34, w: int = 1600, h: int = 1100) -> Image.Image:
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=size)
    y = 60
    for line in lines:
        d.text((60, y), line, fill="black", font=font)
        y += int(size * 1.6)
    return img


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def text_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    body = ("# Primera llei de la termodinàmica\n\n" + " ".join(PROSE) + "\n\n"
            "La energía interna de un sistema cerrado cambia cuando el sistema intercambia calor o trabajo "
            "con su entorno. En clase vimos el convenio de signos y un ejemplo con un pistón.")
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), body, fontsize=11)
    return doc.tobytes()


def garbled_pdf() -> bytes:
    """Correct glyphs on the page, but a garbage text layer (like a broken font encoding / bad OCR layer)."""
    doc = pymupdf.open()
    page = doc.new_page(width=800, height=550)
    page.insert_image(page.rect, stream=_png(render_lines(PROSE)))
    gibberish = " ".join("xqzv kjhw pqlm trbn wqzx vbnq" for _ in range(20))
    page.insert_textbox(pymupdf.Rect(20, 20, 780, 530), gibberish, fontsize=9, render_mode=3)  # invisible text
    return doc.tobytes()


def scanned_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=800, height=550)
    page.insert_image(page.rect, stream=_png(render_lines(PROSE)))
    return doc.tobytes()


def handwriting_photo() -> bytes:
    """Blurry, noisy, rotated, low-contrast phone photo: local OCR confidence drops → vision escalation."""
    img = cv2.cvtColor(np.array(render_lines(PROSE, size=30)), cv2.COLOR_RGB2BGR)
    rng = np.random.default_rng(0)
    img = cv2.GaussianBlur(img, (0, 0), 2.2)
    img = np.clip(img * 0.6 + 80 + rng.normal(0, 45, img.shape), 0, 255).astype(np.uint8)
    h, w = img.shape[:2]
    img = cv2.warpAffine(img, cv2.getRotationMatrix2D((w / 2, h / 2), 4, 1), (w, h), borderValue=(200, 200, 200))
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return buf.tobytes()


def equation_page() -> bytes:
    return _png(render_lines(EQUATIONS))


def clean_photo() -> bytes:
    return _png(render_lines(PROSE))


# ------------------------------------------------------------------ timetables (onboarding)
# The ground truth every timetable fixture encodes: (subject, weekday, start, end, room, professor)
TIMETABLE = [
    ("Thermodynamics", 0, "09:00", "11:00", "Aula A2-101", "Garcia"),
    ("Fluid Dynamics", 1, "11:00", "13:00", "Aula TV1-102", "Puig"),
    ("Calculus II", 2, "08:00", "10:00", "Aula 3", "Serra"),
    ("Thermodynamics", 3, "09:00", "11:00", "Aula A2-101", "Garcia"),
    ("Physics Lab", 4, "12:00", "14:00", "Lab C4-005", "Vidal"),
]
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
_COLORS = {"Thermodynamics": (222, 219, 255), "Fluid Dynamics": (219, 234, 255), "Calculus II": (255, 236, 214),
           "Physics Lab": (214, 245, 228)}
_T0, _ROW, _LEFT, _TOP, _COL = 8, 90, 150, 110, 250  # grid starts 08:00, 90 px per hour


def _grid_geometry(start: str, end: str, weekday: int) -> tuple[int, int, int, int]:
    def y(hhmm: str) -> int:
        h, m = map(int, hhmm.split(":"))
        return _TOP + int(((h - _T0) + m / 60) * _ROW)
    x0 = _LEFT + weekday * _COL
    return x0 + 6, y(start) + 4, x0 + _COL - 6, y(end) - 4


def timetable_image() -> Image.Image:
    """A clean screenshot of a weekly timetable (virtual-campus style: coloured blocks on a grid)."""
    w, h = _LEFT + 5 * _COL + 40, _TOP + 7 * _ROW + 40
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    font, small, head = (ImageFont.load_default(size=s) for s in (22, 18, 24))
    for i, day in enumerate(_DAYS):
        d.text((_LEFT + i * _COL + 70, 50), day, fill=(40, 40, 60), font=head)
    for r in range(8):
        yy = _TOP + r * _ROW
        d.line([(_LEFT, yy), (w - 40, yy)], fill=(225, 225, 232), width=1)
        if r < 7:
            d.text((40, yy + _ROW // 2 - 12), f"{_T0 + r:02d}:00", fill=(110, 110, 125), font=small)
    for subject, wd, s, e, room, prof in TIMETABLE:
        x0, y0, x1, y1 = _grid_geometry(s, e, wd)
        d.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=_COLORS[subject])
        d.text((x0 + 12, y0 + 14), subject, fill=(25, 30, 55), font=font)
        d.text((x0 + 12, y0 + 50), room, fill=(70, 70, 90), font=small)
        d.text((x0 + 12, y0 + 80), f"Prof. {prof}", fill=(70, 70, 90), font=small)
    return img


def timetable_screenshot() -> bytes:
    return _png(timetable_image())


def timetable_photo() -> bytes:
    """The same timetable shot with a phone: perspective (taken at an angle), paper tone, blur, noise, JPEG."""
    src = cv2.cvtColor(np.asarray(timetable_image()), cv2.COLOR_RGB2BGR)
    h, w = src.shape[:2]
    canvas = np.full((h + 240, w + 240, 3), (92, 96, 104), np.uint8)  # desk
    pts_src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    pts_dst = np.float32([[170, 90], [w + 60, 150], [w + 110, h + 200], [120, h + 150]])
    m = cv2.getPerspectiveTransform(pts_src, pts_dst)
    warped = cv2.warpPerspective(src, m, (w + 240, h + 240), dst=canvas, borderMode=cv2.BORDER_TRANSPARENT)
    warped = (warped.astype(np.float32) * np.array([0.93, 0.97, 1.0])).clip(0, 255).astype(np.uint8)  # warm light
    warped = cv2.GaussianBlur(warped, (3, 3), 0)
    noise = np.random.default_rng(7).normal(0, 6, warped.shape)
    warped = (warped.astype(np.float32) + noise).clip(0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 82])
    assert ok
    return buf.tobytes()


def timetable_pdf() -> bytes:
    """A timetable exported as PDF with a real text layer (e.g. from the university's timetable site)."""
    doc = pymupdf.open()
    page = doc.new_page(width=_LEFT + 5 * _COL + 40, height=_TOP + 7 * _ROW + 40)
    for i, day in enumerate(_DAYS):
        page.insert_text((_LEFT + i * _COL + 70, 70), day, fontsize=16)
    for r in range(7):
        page.insert_text((40, _TOP + r * _ROW + _ROW / 2 + 5), f"{_T0 + r:02d}:00", fontsize=12)
    for subject, wd, s, e, room, prof in TIMETABLE:
        x0, y0, x1, y1 = _grid_geometry(s, e, wd)
        rgb = tuple(c / 255 for c in _COLORS[subject])
        page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=rgb, fill=rgb)
        page.insert_text((x0 + 10, y0 + 24), subject, fontsize=14)
        page.insert_text((x0 + 10, y0 + 50), room, fontsize=11)
        page.insert_text((x0 + 10, y0 + 72), f"Prof. {prof}", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def timetable_ics() -> bytes:
    by = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR"}
    events = []
    for i, (subject, wd, s, e, room, prof) in enumerate(TIMETABLE):
        day = 14 + wd  # week of Mon 2026-09-14
        events.append("\r\n".join([
            "BEGIN:VEVENT", f"UID:{i}@campus.example", f"SUMMARY:{subject}",
            f"DTSTART;TZID=Europe/Madrid:202609{day:02d}T{s.replace(':', '')}00",
            f"DTEND;TZID=Europe/Madrid:202609{day:02d}T{e.replace(':', '')}00",
            f"RRULE:FREQ=WEEKLY;BYDAY={by[wd]};UNTIL=20270130T000000Z", f"LOCATION:{room}",
            f"DESCRIPTION:Professor {prof}", "END:VEVENT"]))
    events.append("\r\n".join(["BEGIN:VEVENT", "UID:exam@campus.example", "SUMMARY:Examen final Thermodynamics",
                               "DTSTART;VALUE=DATE:20270115", "END:VEVENT"]))
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Campus//EN\r\n" + "\r\n".join(events)
            + "\r\nEND:VCALENDAR\r\n").encode()


TIMETABLE_TEXT = """Monday 9:00-11:00 Thermodynamics, Aula A2-101, Prof. Garcia
Tuesday 11:00-13:00 Fluid Dynamics - Aula TV1-102 - Prof. Puig
Wed 8-10 Calculus II, Aula 3, Prof. Serra
Thursday 09:00 - 11:00 Thermodynamics, Aula A2-101, Prof. Garcia
Friday 12:00-14:00 Physics Lab, Lab C4-005, Prof. Vidal
"""


# ------------------------------------------------------------------ connected calendar + course guide
def moodle_calendar(today: date, exam_day_offset: int = 30, due_offset: int = 5) -> bytes:
    """A Moodle-style calendar export: due instants, a quiz close, an exam, noise the sync must ignore."""
    def z(d: date, hm: str) -> str:
        return f"{d:%Y%m%d}T{hm.replace(':', '')}00Z"
    due = today + timedelta(days=due_offset)
    ev = [
        ("due1@atenea", "Lab report 1 is due", "Thermodynamics", z(due, "21:59"), z(due, "21:59"), False),
        ("quiz1@atenea", "Quiz 2 closes", "Fluid Dynamics", z(today + timedelta(days=9), "20:00"),
         z(today + timedelta(days=9), "20:00"), False),
        ("exam1@atenea", "Thermodynamics final exam", "Thermodynamics", f"{today + timedelta(days=exam_day_offset):%Y%m%d}",
         None, False),
        ("far@atenea", "Essay is due", "History of Art", z(today + timedelta(days=12), "10:00"),
         z(today + timedelta(days=12), "10:00"), False),  # no such course → unmatched
        ("tut@atenea", "Office hours", "Thermodynamics", z(today + timedelta(days=2), "10:00"),
         z(today + timedelta(days=2), "11:00"), False),  # not a deadline → ignored
        ("weekly@atenea", "Thermodynamics lecture", "Thermodynamics", z(today, "09:00"), z(today, "11:00"), True),
    ]
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Moodle Pty Ltd//NONSGML Moodle Version 2025//EN"]
    for uid, summary, cat, start, end, weekly in ev:
        out += ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{summary}", f"CATEGORIES:{cat}",
                f"DTSTART;VALUE=DATE:{start}" if end is None and len(start) == 8 else f"DTSTART:{start}"]
        if end:
            out.append(f"DTEND:{end}")
        if weekly:
            out.append("RRULE:FREQ=WEEKLY;COUNT=10")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(out).encode()


def upc_guide_pdf(code: str = "300021") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    for line in ["Guia docent", f"{code} - TERMO - Thermodynamics", "Unitat responsable: 300 - EETAC",
                 "OBJECTIUS D'APRENENTATGE DE L'ASSIGNATURA", "Understand energy balances.", "CONTINGUTS",
                 "1. First law of thermodynamics", "Descripció:", "Closed and open systems.", "Dedicació: 20h",
                 "Grup gran/Teoria: 6h", "Aprenentatge autònom: 14h", "Pàgina: 1 / 3",
                 "2. Second law and entropy", "3. Thermodynamic cycles", "ACTIVITATS", "Lab sessions"]:
        page.insert_text((50, y), line, fontsize=11)
        y += 20
    data = doc.tobytes()
    doc.close()
    return data
