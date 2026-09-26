"""Deterministic command parsing: intents, dates, durations, topics, fuzzy matching (no LLM)."""

from __future__ import annotations

from datetime import date

import pytest

from app.command.parse import best_match, parse, parse_date, parse_duration

TODAY = date(2026, 10, 1)  # Thursday


@pytest.mark.parametrize(("text", "intent"), [
    ("make me a 1h exam on entropy", "generate_exam"),
    ("generate a practice exam for Thermo", "generate_exam"),
    ("hazme un examen de 30 min sobre entropía", "generate_exam"),
    ("what did we cover last week in Fluids?", "ask_course"),
    ("explain the Clausius inequality", "ask_course"),
    ("qué vimos ayer en termo", "ask_course"),
    ("move my Thermo exam to the 15th", "change_exam_date"),
    ("postpone the fluids midterm to 20/10", "change_exam_date"),
    ("mou l'examen de termo al 15 d'octubre", "change_exam_date"),
    ("open settings", "open"),
    ("banana", "unknown"),
])
def test_intents(text: str, intent: str) -> None:
    assert parse(text, TODAY).intent == intent


def test_slots() -> None:
    p = parse("make me a 1h exam on entropy", TODAY)
    assert p.duration_minutes == 60 and p.topic == "entropy"
    assert parse("move my Thermo exam to the 15th", TODAY).date == date(2026, 10, 15)
    rng = parse("what did we cover last week in Fluids?", TODAY).date_range
    assert rng is not None and (rng.since, rng.until) == (date(2026, 9, 21), date(2026, 9, 27))
    assert parse("open exams", TODAY).route == "/exams"


@pytest.mark.parametrize(("text", "expected"), [
    ("the 15th", date(2026, 10, 15)),
    ("the 3rd", date(2026, 10, 3)),
    ("2026-12-01", date(2026, 12, 1)),
    ("20/10", date(2026, 10, 20)),
    ("oct 22", date(2026, 10, 22)),
    ("15 de octubre", date(2026, 10, 15)),
    ("tomorrow", date(2026, 10, 2)),
    ("friday", date(2026, 10, 2)),
    ("in 10 days", date(2026, 10, 11)),
])
def test_dates(text: str, expected: date) -> None:
    assert parse_date(text, TODAY) == expected


def test_durations() -> None:
    assert parse_duration("a 1.5h exam") == 90
    assert parse_duration("45 min") == 45
    assert parse_duration("an hour") == 60
    assert parse_duration("no time given") is None


def test_fuzzy_matching() -> None:
    courses = [("t", "Thermodynamics"), ("f", "Fluid Dynamics"), ("c", "Calculus II")]
    assert best_match("my thermo exam", courses) == ("t", [])
    assert best_match("last week in Fluids", courses) == ("f", [])
    assert parse_date("the 3rd", date(2026, 10, 20)) == date(2026, 11, 3)  # already past → next month
    assert best_match("calculus", [("a", "Calculus I"), ("b", "Calculus II")]) == (None, ["b", "a"]) or \
        best_match("calculus", [("a", "Calculus I"), ("b", "Calculus II")])[0] is None
    assert best_match("banana", courses) == (None, [])


def test_timetable_acronyms_match_moodle_full_names() -> None:
    courses = [("mf", "MF(G)"), ("eg", "ELECTRI(G)"), ("ep", "ELECTRI(P)"), ("i2", "I2(P)")]
    assert best_match("MECÀNICA DE FLUIDS (Curs T1) Pràctica 1 es tanca", courses) == ("mf", [])
    assert best_match("INFORMÀTICA II lliurament", courses) == ("i2", [])
    assert best_match("ELECTRICITAT Quiz 2 closes", courses) == ("eg", [])  # G/P groups of one subject
    assert best_match("Assignatures del primer curs (1A i 1B) es tanca", courses) == (None, [])


@pytest.mark.parametrize("text", ["are you connected to my atenea tasks?", "is my calendar synced?",
                                  "estàs connectat a l'atenea?"])
def test_status_questions_are_answered_without_ai(text: str) -> None:
    assert parse(text, TODAY).intent == "status"
