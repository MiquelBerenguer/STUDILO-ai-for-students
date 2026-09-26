"""Plain-language labels for agent steps and runs (UX.md §5: "visible work").

Labels are derived only from what the step actually recorded (tool name, arguments, result), so the live
view can never claim work that did not happen.
"""

from __future__ import annotations

from typing import Any

AGENT_NAMES = {
    "planner": "Planner", "ingestion": "Reading agent", "notes": "Notes agent", "course_memory": "Course memory agent",
    "exam": "Exam agent", "qa": "Q&A agent", "catch_up": "Catch-up agent", "onboarding": "Timetable agent", "calendar": "Calendar agent",
}

_TYPE_NAMES = {"pdf": "PDF", "jpeg": "photo (JPEG)", "png": "image (PNG)", "heic": "photo (HEIC)", "webp": "image",
               "tiff": "scan (TIFF)", "text": "typed text"}


def _g(d: Any, key: str, default: Any = "") -> Any:
    return d.get(key, default) if isinstance(d, dict) else default


def _short(text: Any, n: int = 70) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def describe_step(kind: str, name: str, inp: Any, out: Any, ok: bool = True) -> str:
    if not ok:
        return f"Hit a problem in {name.replace('_', ' ')}: {_short(_g(out, 'error'), 90)} — retrying or moving on"
    if kind == "llm":
        model = name.split("/", 1)[-1]
        calls = _g(out, "tool_calls", [])
        return f"Thinking ({model})" + (f" → {', '.join(c.replace('_', ' ') for c in calls[:3])}" if calls else "")
    if kind == "decision":
        return {
            "escalate_to_vision": f"Escalating to AI: {_short(_g(out, 'reason'), 80)}",
            "page_needs_ocr": f"Page {_g(out, 'page')}: text layer unreadable — trying local OCR",
            "class_ended": f"{_g(out, 'course')} class ended ({_g(out, 'end')})",
            "missed_upload": "No notes arrived in time — flagging the class",
            "exam_approaching": f"{_g(out, 'exam')} is {_g(out, 'days_left')} days away ({_g(out, 'threshold')})",
            "ask_exam_date": f"Asking when the {_g(out, 'course')} exam is",
            "session_state": f"Class session is now {str(_g(out, 'state')).replace('_', ' ')}",
            "calendar_synced": f"Filed {_g(out, 'new')} new and {_g(out, 'updated')} updated deadlines"
                               + (f"; {_g(out, 'unmatched')} didn't match a course" if _g(out, "unmatched") else ""),
            "grid_parse": f"Read the timetable grid: {_g(out, 'slots')} classes found (confidence {_g(out, 'confidence')})",
            "escalate_timetable": f"Escalating to AI: {_short(_g(out, 'reason'), 80)}",
        }.get(name, name.replace("_", " ").capitalize())
    # tools
    if name == "detect_type":
        return f"Checking what kind of file this is — {_TYPE_NAMES.get(_g(out, 'type'), _g(out, 'type'))}"
    if name == "extract_text":
        pages = _g(out, "pages", [])
        return f"Reading the text layer — {len(pages)} page(s)" if len(pages) != 1 or _g(pages[0], "images", None) is not None \
            else "Reading your typed text"
    if name == "check_legibility":
        page = _g(inp, "page")
        return (f"Page {page}: text was clear — no AI needed" if _g(out, "passed")
                else f"Page {page}: {_short(_g(out, 'reason'), 60)} — trying OCR")
    if name == "run_ocr":
        return ("Reading your photo… clear print — no AI needed" if _g(out, "action") == "accept_ocr"
                else f"Reading your photo… {_short(_g(out, 'reason'), 80)}")
    if name == "vision_transcribe":
        if _g(out, "degraded"):
            return "AI transcription unavailable — kept the local OCR text"
        return f"Transcribed with AI ({_g(out, 'model')}, ${_g(out, 'cost_usd', 0)})"
    if name == "classify_topic":
        return f"Adding to topic: {_g(out, 'title')}" + (" (new topic)" if _g(out, "is_new") else "")
    if name == "get_topic_note":
        return f"Reading your “{_g(out, 'title')}” note"
    if name == "update_topic_note":
        verb = "Writing" if _g(inp, "operation") == "append_section" else "Updating"
        heading = _g(inp, "heading") or "a section"
        return f"{verb} “{_short(heading, 50)}” in your notes"
    if name == "create_topic":
        return f"Creating topic “{_g(inp, 'title')}”"
    if name == "search_notes":
        return f"Searching your notes for “{_short(_g(inp, 'query'), 50)}”"
    if name == "link_source":
        return "Linking the source file to your notes"
    if name == "get_sessions":
        return "Reviewing your recent classes"
    if name == "append_session_summary":
        return "Writing what was covered in this class"
    if name == "update_course_pace":
        return f"Updating course pace — {_short(_g(inp, 'syllabus_position'), 60)}"
    if name == "flag_missed_session":
        return "Flagging the class as missed in course memory"
    if name == "add_open_question":
        return f"Noting an open question: {_short(_g(inp, 'text'), 60)}"
    if name == "link_topics":
        return "Linking topics that build on each other"
    if name == "get_exam_scope":
        return "Working out what goes into the exam"
    if name == "get_past_exams":
        return "Looking at past exams for style and difficulty"
    if name == "read_sections":
        return f"Reading {len(_g(inp, 'section_ids', []))} note section(s)"
    if name == "add_study_guide_section":
        return f"Writing study guide: {_short(_g(inp, 'heading'), 50)}"
    if name == "draft_question":
        if _g(inp, "replaces_question_id"):
            return "Rewriting a question that failed the check"
        return f"Drafting a question for practice exam {_g(inp, 'practice_exam_number')}"
    if name == "verify_question":
        if _g(out, "passed"):
            return "Checking a question — solvable, units OK, backed by your notes"
        issues = _g(out, "issues", [])
        return f"Checking a question — failed ({_short(issues[0] if issues else 'see trace', 50)}), rewriting it"
    if name == "save_exam_pack":
        return "Saving the Exam Pack"
    if name == "create_reminder":
        return f"Putting a card in your feed: {_short(_g(inp, 'title'), 60)}"
    if name == "schedule_job":
        return f"Scheduling a follow-up check for {str(_g(inp, 'run_after'))[:16].replace('T', ' ')}"
    if name == "get_course_sessions":
        return f"Looking at your classes{(' from ' + str(_g(inp, 'since'))) if _g(inp, 'since') else ''}"
    if name == "answer":
        return "Answer ready"
    if name == "finish":
        return f"Done: {_short(_g(out, 'summary') or _g(inp, 'summary'), 80)}"
    if name == "fetch_calendar":
        return f"Reading your calendar from {_g(inp, 'host')}"
    if name in ("parse_timetable", "extract_timetable"):
        return f"Reading your timetable — {_short(_g(out, 'summary'), 70)}"
    if name == "validate_timetable":
        return f"Checking the result — {_g(out, 'slots')} classes, {_g(out, 'low_confidence')} to double-check"
    return name.replace("_", " ").capitalize()


def describe_run(agent: str, goal: str, output: str, state: str) -> str:
    head = AGENT_NAMES.get(agent, agent.replace("_", " ").title())
    what = _short(goal.splitlines()[0] if goal else "", 90)
    verb = {"running": "is working on", "succeeded": "finished", "failed": "failed on",
            "step_limit": "stopped (step limit) on"}.get(state, state)
    return f"{head} {verb}: {what}"


def headline(agent: str, output: str, state: str) -> str:
    """One plain sentence for a finished run (the raw output stays in the trace for Activity)."""
    import json
    import re

    if state != "succeeded":
        return {"failed": "Couldn't finish — see the steps", "step_limit": "Stopped before finishing"}.get(state, state)
    out = (output or "").strip()
    if out.startswith("{"):
        try:
            data = json.loads(out)
            out = str(data.get("summary") or data.get("answer_md") or out)
        except ValueError:
            pass
    if agent == "planner":
        parts = []
        for seg in filter(None, (s.strip() for s in out.split(";"))):
            if m := re.match(r"class_ended (.+) \d{4}-\d\d-\d\d$", seg):
                parts.append(f"Noticed your {m.group(1)} class ended")
            elif seg.startswith("missed "):
                parts.append("Flagged a class that got no notes")
            elif m := re.match(r"exam_approaching (.+) (T-\d+)$", seg):
                parts.append(f"{m.group(1)} is getting close ({m.group(2)})")
            elif seg == "session awaiting_upload":
                parts.append("Asked for your notes")
            elif seg.startswith("nothing to do"):
                parts.append("Checked — nothing to do")
            elif m := re.match(r"calendar_sync (.+)$", seg):
                parts.append(f"Refreshing your {m.group(1)} calendar")
            elif seg.startswith("session "):
                parts.append("Updated the class session")
        return "; ".join(parts) or "Checked your schedule"
    if agent == "calendar" and out:
        return f"Calendar refreshed: {out}"
    if agent == "course_memory" and out == "session flagged as missed":
        return "Flagged the class as missed in your course memory"
    if agent == "onboarding" and (m := re.match(r"(\d+) classes via (\w+)", out)):
        how = {"grid": "no AI needed", "ics": "no AI needed", "text": "no AI needed"}.get(m.group(2), "with the AI reader")
        return f"Read {m.group(1)} classes from your timetable ({how})"
    if agent == "ingestion" and (m := re.search(r"topic=([^;]+)", out)):
        topic = m.group(1).strip()
        return f"Read your file → {topic}" if topic and topic != "None" else "Read your file"
    return _short(out, 110) or "Done"
