"""Deterministic command parsing (UX.md §6): intents, dates, durations, fuzzy course/exam matching.

Pure functions, no I/O. English, Spanish and Catalan keywords. The LLM fallback lives in service.py and is
used only when no rule matches.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

Intent = Literal["generate_exam", "ask_course", "change_exam_date", "open", "status", "unknown"]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


_WORD = re.compile(r"[a-z0-9]+")

MONTHS = {
    "jan": 1, "january": 1, "ene": 1, "enero": 1, "gen": 1, "gener": 1,
    "feb": 2, "february": 2, "febrero": 2, "febrer": 2,
    "mar": 3, "march": 3, "marzo": 3, "marc": 3,
    "apr": 4, "april": 4, "abr": 4, "abril": 4,
    "may": 5, "mayo": 5, "maig": 5,
    "jun": 6, "june": 6, "junio": 6, "juny": 6,
    "jul": 7, "july": 7, "julio": 7, "juliol": 7,
    "aug": 8, "august": 8, "ago": 8, "agosto": 8, "agost": 8,
    "sep": 9, "sept": 9, "september": 9, "septiembre": 9, "setembre": 9,
    "oct": 10, "october": 10, "octubre": 10,
    "nov": 11, "november": 11, "noviembre": 11, "novembre": 11,
    "dec": 12, "december": 12, "dic": 12, "diciembre": 12, "des": 12, "desembre": 12,
}
WEEKDAYS = {
    "monday": 0, "mon": 0, "lunes": 0, "dilluns": 0, "tuesday": 1, "tue": 1, "martes": 1, "dimarts": 1,
    "wednesday": 2, "wed": 2, "miercoles": 2, "dimecres": 2, "thursday": 3, "thu": 3, "jueves": 3, "dijous": 3,
    "friday": 4, "fri": 4, "viernes": 4, "divendres": 4, "saturday": 5, "sat": 5, "sabado": 5, "dissabte": 5,
    "sunday": 6, "sun": 6, "domingo": 6, "diumenge": 6,
}

_MOVE = re.compile(r"\b(move|change|reschedule|postpone|push|shift|bring forward|set|mou|moure|mueve|mover|cambia|cambiar|"
                   r"canvia|canviar|aplaza|aplazar|ajorna|ajornar|pasa|passa)\b")
_EXAM_WORD = re.compile(r"\b(exam|exams|midterm|final|test|quiz|examen|examenes|parcial|prova|practice)\b")
_MAKE = re.compile(r"\b(make|create|generate|build|give|prepare|write|crea|crear|genera|generar|haz|hazme|fes|fes-me|"
                   r"prepara|preparame|dame|dona'm|donam)\b")
_ASK = re.compile(r"^(what|whats|how|why|when|which|who|explain|summari[sz]e|summary|remind|did|do|does|is|are|can|"
                  r"que|qu[eé]|como|cuando|cual|explica|resume|resumen|quin|quina|com|quan|per que)\b")
# "Are you connected to my Atenea tasks?", "is my calendar synced?": answered from Novi's own records (no AI).
_STATUS = re.compile(r"\b(connected|connect|conectad[oa]|connectat|sync|synced|syncing|sincroniz\w*|linked|vinculad\w*|"
                     r"atenea|moodle|calendar|calendari|calendario)\b")
_OPEN = re.compile(r"\b(open|show|go to|take me to|abre|abrir|obre|obrir|mostra|ensenya|muestra|ver)\b")


@dataclass
class DateRange:
    since: date | None = None
    until: date | None = None
    label: str = ""


@dataclass
class Parsed:
    intent: Intent
    text: str
    date: date | None = None
    duration_minutes: int | None = None
    topic: str | None = None
    date_range: DateRange | None = None
    route: str | None = None
    signals: list[str] = field(default_factory=list)


def parse_duration(t: str) -> int | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(h|hr|hrs|hour|hours|hora|horas|hores)\b", t)
    if m:
        return int(round(float(m.group(1).replace(",", ".")) * 60))
    m = re.search(r"\b(an|one|a|una|un)\s+(hour|hora)\b", t)
    if m:
        return 60
    m = re.search(r"(\d+)\s*(m|min|mins|minute|minutes|minuto|minutos|minuts)\b", t)
    if m:
        return int(m.group(1))
    if re.search(r"\b(half an hour|media hora|mitja hora)\b", t):
        return 30
    return None


def _next_dom(day: int, today: date) -> date | None:
    """Next occurrence of a day-of-month (today counts)."""
    for add in range(0, 3):
        y, m = today.year + (today.month - 1 + add) // 12, (today.month - 1 + add) % 12 + 1
        try:
            d = date(y, m, day)
        except ValueError:
            continue
        if d >= today:
            return d
    return None


def parse_date(t: str, today: date) -> date | None:
    m = re.search(r"\b(20\d\d)-(\d{1,2})-(\d{1,2})\b", t)
    if m:
        return _safe(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        d = _safe(y, int(m.group(2)), int(m.group(1)))  # day/month (European)
        if d and not m.group(3) and d < today:
            d = _safe(y + 1, int(m.group(2)), int(m.group(1)))
        return d
    words = _WORD.findall(t)
    for i, w in enumerate(words):
        if w in MONTHS:
            month = MONTHS[w]
            day = None
            if i + 1 < len(words) and re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", words[i + 1]):
                day = int(re.match(r"\d+", words[i + 1]).group())  # type: ignore[union-attr]
            elif i >= 1 and re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", words[i - 1]):
                day = int(re.match(r"\d+", words[i - 1]).group())  # type: ignore[union-attr]
            elif i >= 2 and words[i - 1] == "de" and re.fullmatch(r"\d{1,2}", words[i - 2]):
                day = int(words[i - 2])
            if day:
                d = _safe(today.year, month, day)
                return d if d is None or d >= today else _safe(today.year + 1, month, day)
    if re.search(r"\b(tomorrow|manana|dema)\b", t):
        return today + timedelta(days=1)
    if re.search(r"\b(today|hoy|avui)\b", t):
        return today
    m = re.search(r"\bin (\d+) days?\b|\ben (\d+) dias\b|\bd'aqui a (\d+) dies\b", t)
    if m:
        return today + timedelta(days=int(next(g for g in m.groups() if g)))
    for w in words:
        if w in WEEKDAYS and w not in ("mar", "sat", "sun", "wed"):  # ambiguous tokens need full names
            return today + timedelta(days=(WEEKDAYS[w] - today.weekday()) % 7 or 7)
    m = re.search(r"\b(?:the|el|dia|day|on)\s+(\d{1,2})(?:st|nd|rd|th)?\b", t) or \
        re.search(r"\b(\d{1,2})(st|nd|rd|th)\b", t)
    if m:
        return _next_dom(int(m.group(1)), today)
    return None


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_range(t: str, today: date) -> DateRange | None:
    monday = today - timedelta(days=today.weekday())
    if re.search(r"\b(last week|past week|semana pasada|setmana passada)\b", t):
        return DateRange(monday - timedelta(days=7), monday - timedelta(days=1), "last week")
    if re.search(r"\b(this week|esta semana|aquesta setmana)\b", t):
        return DateRange(monday, today, "this week")
    if re.search(r"\b(yesterday|ayer|ahir)\b", t):
        return DateRange(today - timedelta(days=1), today - timedelta(days=1), "yesterday")
    if re.search(r"\b(today|hoy|avui)\b", t):
        return DateRange(today, today, "today")
    m = re.search(r"\blast (\d+) days\b|\bultimos (\d+) dias\b", t)
    if m:
        n = int(next(g for g in m.groups() if g))
        return DateRange(today - timedelta(days=n), today, f"last {n} days")
    return None


def parse_topic(t: str) -> str | None:
    m = re.search(r"\b(?:on|about|covering|sobre|de|del|acerca de)\s+(.+?)(?:\s+for\s+.*|\s+in\s+\d.*|[?.!]|$)", t)
    if not m:
        return None
    topic = re.sub(r"\b(\d+(?:[.,]\d+)?\s*(h|hour|hours|min|mins|minutes|hora|horas))\b", "", m.group(1)).strip(" ,.")
    topic = re.sub(r"^(the|el|la|los|las|els|les)\s+", "", topic)
    return topic or None


ROUTES = [
    (re.compile(r"\b(exam|exams|pack|packs|examen|examenes)\b"), "/exams"),
    (re.compile(r"\b(activity|costs|cost|runs|actividad|activitat)\b"), "/activity"),
    (re.compile(r"\b(settings|ajustes|configuracion|configuracio)\b"), "/settings"),
    (re.compile(r"\b(schedule|timetable|week|horario|horari)\b"), "/schedule"),
    (re.compile(r"\b(upload|subir|pujar)\b"), "/upload"),
]


def parse(text: str, today: date) -> Parsed:
    t = norm(text).strip()
    p = Parsed(intent="unknown", text=text.strip())
    p.date = parse_date(t, today)
    p.duration_minutes = parse_duration(t)
    p.date_range = parse_range(t, today)
    if _MOVE.search(t) and _EXAM_WORD.search(t) and not _MAKE.search(t):
        p.intent, p.signals = "change_exam_date", ["move-verb", "exam-word"]
    elif _MAKE.search(t) and _EXAM_WORD.search(t):
        p.intent, p.signals = "generate_exam", ["make-verb", "exam-word"]
        p.topic = parse_topic(t)
    elif _STATUS.search(t) and (t.endswith("?") or _ASK.search(t) or re.search(r"\bstatus|estado|estat\b", t)):
        p.intent, p.signals = "status", ["status-question"]
    elif _OPEN.search(t) and not t.endswith("?"):
        p.intent, p.signals = "open", ["open-verb"]
        p.route = next((r for rx, r in ROUTES if rx.search(t)), None)
    elif t.endswith("?") or _ASK.search(t):
        p.intent, p.signals = "ask_course", ["question"]
    return p


# ------------------------------------------------------------------ fuzzy matching of courses / exams
def _tokens(s: str) -> list[str]:
    return [w for w in _WORD.findall(norm(s)) if len(w) >= 2]


STOP = {"exam", "the", "my", "on", "in", "to", "de", "del", "la", "el", "for", "about", "what", "did", "we", "last",
        "week", "cover", "covered", "move", "make", "me", "an", "a", "of", "and", "i", "is", "this", "que", "hem",
        "examen", "final", "midterm", "parcial", "test", "quiz", "practice", "hour", "h"}


# Class-group markers timetables append to subject names: "MF(G)" (grup gran), "ELECTRI(P)" (pràctiques).
GROUP_SUFFIX = re.compile(r"\s*\((G|P|T|L|GG|GP|GM|LAB|TEO|PRA|PRAC|TEORIA|PRACTIQUES)\)\s*$", re.I)
_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
_INITIAL_STOP = {"de", "del", "la", "les", "els", "el", "i", "y", "e", "the", "of", "and", "a", "per", "para", "en"}


def strip_group(name: str) -> str:
    return GROUP_SUFFIX.sub("", name).strip()


def _acronym_hit(acronym: str, query: str) -> bool:
    """'mf' ~ 'MECÀNICA DE FLUIDS', 'i2' ~ 'INFORMÀTICA II': initials of consecutive content words."""
    words = [w for w in _WORD.findall(norm(query)) if w not in _INITIAL_STOP]
    initials = "".join(_ROMAN.get(w, w[0]) for w in words)
    return len(acronym) >= 2 and acronym in initials


def match_score(query: str, name: str) -> float:
    """Token overlap with prefix matching ("thermo" ~ "thermodynamics", "fluids" ~ "fluid"), plus acronyms
    ("MF" ~ "Mecànica de Fluids") because timetables often use subject acronyms while Moodle uses full names."""
    q = [w for w in _tokens(query) if w not in STOP]
    n = _tokens(strip_group(name))
    score = 0.0
    bare = norm(strip_group(name)).replace(" ", "")
    if re.fullmatch(r"[a-z]{1,6}\d?", bare) and _acronym_hit(bare, query):
        score += 1.5
    for w in q:
        for x in n:
            if w == x:
                score += 1.0
            elif len(w) >= 4 and (x.startswith(w) or w.startswith(x)) and min(len(w), len(x)) >= 4:
                score += 0.8
            elif len(w) >= 5 and len(x) >= 5 and w[:5] == x[:5]:
                score += 0.6
    return score


def best_match(query: str, candidates: list[tuple[str, str]]) -> tuple[str | None, list[str]]:
    """Return (id, []) for a unique best match, (None, [ids…]) when ambiguous, (None, []) when nothing matches."""
    scored = sorted(((match_score(query, name), cid) for cid, name in candidates), reverse=True)
    if not scored or scored[0][0] <= 0:
        return None, []
    top = [cid for s, cid in scored if s == scored[0][0]]
    names = {cid: norm(strip_group(name)) for cid, name in candidates}
    if len(top) > 1 and len({names[c] for c in top}) == 1:  # "ELECTRI(G)" vs "ELECTRI(P)": same subject
        return next(cid for cid, _ in candidates if cid in top), []
    return (top[0], []) if len(top) == 1 else (None, top)
