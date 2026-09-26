"""Shared alert rules (app/alerts.py): pure functions over a snapshot, with a fixed clock."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.alerts import (
    AssignmentIn,
    AttemptIn,
    CardIn,
    CourseIn,
    ExamIn,
    SessionIn,
    SlotIn,
    Snapshot,
    compute_alerts,
    held_classes,
    load_snapshot,
    resolve_context,
    setup_missing,
)

TZ = "Europe/Madrid"
NOW = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)  # Thursday 1 Oct 2026, 12:00 in Madrid
TODAY = date(2026, 10, 1)
LONG_AGO = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
THERMO = CourseIn("c-thermo", "Thermodynamics", "#6558e8", "1. First law\n2. Second law\n3. Cycles")
FLUIDS = CourseIn("c-fluids", "Fluid Dynamics")
MON = SlotIn("s-mon", THERMO.id, 0, "09:00", "11:00", LONG_AGO, "A2-101")  # Mon 28 Sep, held
THU = SlotIn("s-thu", FLUIDS.id, 3, "09:00", "11:00", LONG_AGO)  # today, ended at 11:00 local


def snap(**kw: object) -> Snapshot:
    base: dict[str, object] = {"now": NOW, "tz": TZ, "courses": (THERMO, FLUIDS)}
    base.update(kw)
    return Snapshot(**base)  # type: ignore[arg-type]


def card(kind: str, **kw: object) -> CardIn:
    return CardIn(id=f"card-{kind}", kind=kind, title=f"{kind} title", created_at=NOW - timedelta(hours=1),
                  body="First sentence. Second sentence.",
                  actions=({"id": "approve", "label": "Approve", "type": "button", "primary": True},
                           {"id": "dismiss", "label": "Dismiss", "type": "button"}), **kw)  # type: ignore[arg-type]


# ------------------------------------------------------------------ no data / setup
def test_no_data_means_nothing_pending_and_setup_missing() -> None:
    s = Snapshot(now=NOW, tz=TZ)
    assert compute_alerts(s) == []
    assert setup_missing(s) == ["courses", "schedule", "exam_dates"]
    assert held_classes(s) == []


def test_setup_complete() -> None:
    s = snap(slots=(MON,), exams=(ExamIn("e1", THERMO.id, "Thermo midterm", TODAY + timedelta(days=30)),))
    assert setup_missing(s) == []


# ------------------------------------------------------------------ held classes
def test_held_classes_start_when_the_slot_was_added() -> None:
    added = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)  # Monday 21 Sep, after that day's class
    s = snap(slots=(SlotIn("s", THERMO.id, 0, "09:00", "11:00", added),))
    assert [h.session_date for h in held_classes(s)] == [date(2026, 9, 28)]


def test_held_classes_respect_the_semester_and_the_clock() -> None:
    s = snap(slots=(MON, THU), semester_start=date(2026, 9, 29))
    assert [(h.slot.id, h.session_date) for h in held_classes(s)] == [("s-thu", TODAY)]
    new_thu = SlotIn("s-new", FLUIDS.id, 3, "09:00", "11:00", datetime(2026, 9, 28, 8, 0, tzinfo=UTC))
    before_end = snap(slots=(new_thu,), now=datetime(2026, 10, 1, 8, 30, tzinfo=UTC))  # 10:30 local: in class
    assert held_classes(before_end) == []


def test_first_day_of_the_semester_has_nothing_held() -> None:
    s = snap(slots=(MON, THU), semester_start=TODAY, now=datetime(2026, 10, 1, 6, 0, tzinfo=UTC))
    assert held_classes(s) == [] and compute_alerts(s) == []


def test_today_uses_the_students_timezone() -> None:
    late = datetime(2026, 9, 30, 23, 30, tzinfo=UTC)  # already Thursday 01:30 in Madrid
    assert snap(now=late).today == TODAY
    assert Snapshot(now=late, tz="America/New_York").today == date(2026, 9, 30)


# ------------------------------------------------------------------ missing notes
def test_missing_notes_for_recent_classes_only() -> None:
    s = snap(slots=(MON, THU), sessions=(SessionIn("sess-mon", THERMO.id, MON.id, date(2026, 9, 28), "missed"),))
    alerts = compute_alerts(s)
    assert [a.ref for a in alerts] == [f"missing_notes:{THU.id}@2026-10-01", "missing_notes:sess-mon"]
    today, monday = alerts
    assert today.title == "Notes for today's Fluid Dynamics class" and today.reason == "Class ended at 11:00"
    assert today.actions[0]["params"] == {"course_id": FLUIDS.id, "kind": "notes", "slot_id": THU.id,
                                          "session_date": "2026-10-01"}
    assert monday.title == "Notes for Monday's Thermodynamics class"
    assert monday.actions[0]["params"]["class_session_id"] == "sess-mon"
    assert monday.seed_message == "Help me with the notes from Monday's Thermodynamics class."
    long_ago = snap(slots=(MON,), now=NOW + timedelta(days=10))  # Mon 28 Sep is now 13 days back
    assert [a.session_date for a in compute_alerts(long_ago)] == [date(2026, 10, 5)]


def test_classes_with_notes_are_not_pending() -> None:
    sessions = (SessionIn("a", THERMO.id, MON.id, date(2026, 9, 28), "processed"),
                SessionIn("b", FLUIDS.id, THU.id, TODAY, "uploaded"))
    assert compute_alerts(snap(slots=(MON, THU), sessions=sessions)) == []


def test_missing_notes_merge_the_matching_card() -> None:
    sess = SessionIn("sess-mon", THERMO.id, MON.id, date(2026, 9, 28), "awaiting_upload")
    prompt = CardIn("card-up", "upload_prompt", "Your Thermodynamics class ended", NOW, data={"session_id": "sess-mon"})
    alerts = compute_alerts(snap(slots=(MON,), sessions=(sess,), cards=(prompt,)))
    assert len(alerts) == 1 and alerts[0].card_id == "card-up" and alerts[0].type == "missing_notes"


# ------------------------------------------------------------------ tasks
def test_task_windows_and_tiers() -> None:
    tasks = (AssignmentIn("t-today", THERMO.id, "Lab report 1", TODAY, due_at=datetime(2026, 10, 1, 21, 59, tzinfo=UTC)),
             AssignmentIn("t-3", FLUIDS.id, "Quiz 2", TODAY + timedelta(days=3)),
             AssignmentIn("t-4", FLUIDS.id, "Too far", TODAY + timedelta(days=4)),
             AssignmentIn("t-done", FLUIDS.id, "Done", TODAY, done=True),
             AssignmentIn("t-old", FLUIDS.id, "Way overdue", TODAY - timedelta(days=8)),
             AssignmentIn("t-late", FLUIDS.id, "Late", TODAY - timedelta(days=2)))
    alerts = {a.ref: a for a in compute_alerts(snap(assignments=tasks))}
    assert set(alerts) == {"task_due:t-today", "task_due:t-3", "task_due:t-late"}
    assert alerts["task_due:t-today"].tier == 1 and alerts["task_due:t-today"].reason.endswith("due today at 23:59")
    assert alerts["task_due:t-late"].tier == 1 and "was due" in alerts["task_due:t-late"].reason
    assert alerts["task_due:t-3"].tier == 3
    assert alerts["task_due:t-3"].actions[0]["id"] == "mark_done"


def test_task_merges_the_deadline_card() -> None:
    task = AssignmentIn("t1", THERMO.id, "Lab report 1", TODAY + timedelta(days=1))
    deadline = CardIn("card-dl", "deadline", "Lab report 1 is due", NOW, data={"assignment_id": "t1"})
    [alert] = compute_alerts(snap(assignments=(task,), cards=(deadline,)))
    assert alert.card_id == "card-dl"


# ------------------------------------------------------------------ exams
def test_exam_today_without_practice_is_most_urgent() -> None:
    exam = ExamIn("e1", THERMO.id, "Thermo midterm", TODAY)
    [alert] = compute_alerts(snap(exams=(exam,)))
    assert alert.type == "exam_prep" and alert.tier == 1 and alert.reason == "Exam today · no practice exam yet"
    assert alert.seed_message == "Make me a practice exam for Thermodynamics." and alert.actions == ()


def test_exam_prep_window_and_practice() -> None:
    soon = ExamIn("e1", THERMO.id, "Thermo midterm", TODAY + timedelta(days=5))
    far = ExamIn("e2", FLUIDS.id, "Fluids final", TODAY + timedelta(days=15))
    assert [a.ref for a in compute_alerts(snap(exams=(soon, far)))] == ["exam_prep:e1"]
    practiced = AttemptIn(THERMO.id, "e1", NOW - timedelta(days=1))
    assert compute_alerts(snap(exams=(soon,), attempts=(practiced,))) == []


# ------------------------------------------------------------------ cards
def test_only_actionable_cards_are_pending() -> None:
    cards = tuple(card(k) for k in ("approval", "job_failed", "notes_filed", "account_claim", "syllabus_wanted",
                                    "exam_date_needed", "answer"))
    alerts = compute_alerts(snap(cards=cards))
    assert sorted(a.type for a in alerts) == ["approval", "job_failed"]
    approval = next(a for a in alerts if a.type == "approval")
    assert approval.ref == "pending:card-approval" and approval.reason == "First sentence."
    assert [a["id"] for a in approval.actions] == ["approve"]


# ------------------------------------------------------------------ ordering + all up to date
def test_urgency_order() -> None:
    s = snap(slots=(MON,), cards=(card("approval"),),
             exams=(ExamIn("e1", THERMO.id, "Thermo midterm", TODAY + timedelta(days=5)),),
             assignments=(AssignmentIn("t-today", THERMO.id, "Lab", TODAY),
                          AssignmentIn("t-3", THERMO.id, "Quiz", TODAY + timedelta(days=3))))
    assert [a.type for a in compute_alerts(s)] == ["task_due", "approval", "task_due", "missing_notes", "exam_prep"]


def test_all_up_to_date() -> None:
    s = snap(slots=(MON,), sessions=(SessionIn("a", THERMO.id, MON.id, date(2026, 9, 28), "processed"),),
             exams=(ExamIn("e1", THERMO.id, "Thermo midterm", TODAY + timedelta(days=5)),),
             attempts=(AttemptIn(THERMO.id, "e1", NOW),))
    assert compute_alerts(s) == []


# ------------------------------------------------------------------ Ask Novi handoff
def test_resolve_context() -> None:
    s = snap(slots=(MON,), cards=(card("approval"),))
    all_ = resolve_context(s, "pending:all")
    assert all_ is not None and all_.type == "pending_all" and len(all_.alerts) == 2
    one = resolve_context(s, "pending:card-approval")
    assert one is not None and one.type == "approval" and one.seed_message.startswith("Should I approve")
    assert resolve_context(s, "pending:nope") is None
    assert resolve_context(s, "task_due:nope") is None
    setup = resolve_context(s, "setup:exam_dates")
    assert setup is not None and setup.setup_missing == ("exam_dates",)
    assert setup.seed_message == "Help me finish setting up: add your exam dates."
    done = snap(slots=(MON,), exams=(ExamIn("e1", THERMO.id, "x", TODAY),))
    assert resolve_context(done, "setup:exam_dates") is None


# ------------------------------------------------------------------ loader (real DB, user-scoped)
def test_load_snapshot_is_user_scoped(app) -> None:  # type: ignore[no-untyped-def]
    from app.db.engine import user_session
    from tests.conftest import make_client, onboard, register

    alice, bob = make_client(app), make_client(app)
    alice_id = register(alice, "alice@example.com")["id"]
    register(bob, "bob@example.com")
    onboard(alice)
    bob.post("/api/v1/courses", json={"name": "Bob's secret course"})
    with user_session(alice_id) as db:
        s = load_snapshot(db, now=NOW, tz=TZ)
    assert {c.name for c in s.courses} == {"Thermodynamics", "Fluid Dynamics"}
    assert len(s.slots) == 2 and len(s.exams) == 1 and s.attempts == ()
    assert [c.kind for c in s.cards] == ["past_exams_wanted"]  # created with the exam; not a pending alert
