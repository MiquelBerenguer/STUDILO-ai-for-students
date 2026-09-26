"""Test-only scripted LLM provider. Plays the role of a model that follows the agent prompts.

Registered as provider "scripted" through LLMClient(adapters=..., extra_providers=...); it is never
reachable from production configuration.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.llm.providers import ProviderSpec
from app.llm.types import LLMError, LLMResponse, Message, ToolSpec

SCRIPTED = ProviderSpec("scripted", "scripted", "(test)")
ID = r"[0-9a-f\-]{36}"


def _tool_results(messages: list[Message]) -> list[tuple[str, Any]]:
    out = []
    for m in messages:
        if m["role"] == "tool":
            try:
                out.append((m.get("name", ""), json.loads(m["content"])))  # type: ignore[arg-type]
            except (json.JSONDecodeError, TypeError):
                out.append((m.get("name", ""), m.get("content")))
    return out


def _call(name: str, args: dict[str, Any], i: int = 0) -> dict[str, Any]:
    return {"id": f"call_{name}_{i}", "name": name, "arguments": args}


class ScriptedAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_models: set[str] = set()
        self.verify_fail_once = False
        self._verify_failed: set[str] = set()

    async def test_connection(self, spec: ProviderSpec, key: str | None) -> str:
        return "OK: scripted"

    async def complete(self, spec: ProviderSpec, key: str | None, model: str, messages: list[Message],
                       tools: list[ToolSpec] | None, json_mode: bool, max_tokens: int | None,
                       temperature: float | None) -> LLMResponse:
        self.calls.append({"model": model, "tools": [t["name"] for t in tools or []], "json": json_mode})
        if model in self.fail_models:
            raise LLMError("scripted", model, "HTTP 503: simulated outage", 503)
        text, calls = "", []
        names = {t["name"] for t in tools or []}
        if "update_topic_note" in names:
            calls = self._notes(messages)
        elif "append_session_summary" in names:
            calls = self._memory(messages)
        elif "save_exam_pack" in names:
            calls = self._exam(messages)
        elif "answer" in names:
            calls = self._qa(messages)
        elif model.startswith("vision") and not json_mode:
            text = "# Primera llei de la termodinàmica\n\nEl calor aportat és $Q = \\Delta U + W$.\n\n- Sistema tancat"
        elif json_mode:
            text = self._json(messages)
        else:
            text = "ok"
        return LLMResponse(text=text, tool_calls=calls, input_tokens=1000, output_tokens=200, provider="scripted",
                           model=model)

    # -- notes agent: read topic → append a section citing the upload → finish
    def _notes(self, messages: list[Message]) -> list[dict[str, Any]]:
        goal = str(messages[1]["content"])
        upload_id = re.search(rf"UPLOAD id=({ID})", goal).group(1)  # type: ignore[union-attr]
        topic_id = re.search(rf"ASSIGNED TOPIC id=({ID})", goal).group(1)  # type: ignore[union-attr]
        done = [n for n, _ in _tool_results(messages)]
        if "get_topic_note" not in done:
            return [_call("get_topic_note", {"topic_id": topic_id})]
        if "update_topic_note" not in done:
            content = goal.split("NEW CONTENT (Markdown):", 1)[1].strip()[:1500]
            return [_call("update_topic_note", {"topic_id": topic_id, "operation": "append_section",
                                                "heading": "Class notes", "content_md": content,
                                                "source_upload_ids": [upload_id]})]
        return [_call("finish", {"summary": "Appended the class notes as a new section."})]

    # -- course memory agent
    def _memory(self, messages: list[Message]) -> list[dict[str, Any]]:
        goal = str(messages[1]["content"])
        session_id = re.search(rf"SESSION id=({ID})", goal).group(1)  # type: ignore[union-attr]
        topics = re.findall(ID, goal.split("TOPICS TOUCHED:", 1)[1].split("\n", 1)[0])
        results = _tool_results(messages)
        done = [n for n, _ in results]
        if "get_sessions" not in done:
            return [_call("get_sessions", {"limit": 10})]
        if "append_session_summary" not in done:
            pace = next(r for n, r in results if n == "get_sessions")["computed_pace"]["topics_per_week"]
            return [_call("append_session_summary", {"session_id": session_id, "topic_ids": topics,
                                                     "summary_md": "- Covered the first law of thermodynamics"}, 0),
                    _call("update_course_pace", {"topics_per_week": pace, "syllabus_position": "Unit 1: first law",
                                                 "pace_note": "on track"}, 1),
                    _call("add_open_question", {"text": "Why is work negative when done on the system?"}, 2)]
        return [_call("finish", {"summary": "Memory updated."})]

    # -- exam agent: scope → guide per topic → N×Q questions → verify each (redraft failures) → save
    def _exam(self, messages: list[Message]) -> list[dict[str, Any]]:
        results = _tool_results(messages)
        scope = next((r for n, r in results if n == "get_exam_scope"), None)
        if scope is None:
            return [_call("get_exam_scope", {})]
        topics = [t for t in scope["topics"] if t["sections"]]
        req = scope["requirements"]
        done = [n for n, _ in results]
        if "add_study_guide_section" not in done:
            return [_call("add_study_guide_section", {
                "heading": f"Review: {t['title']}", "topic_id": t["topic_id"],
                "content_md": f"Key ideas of {t['title']}: $Q = \\Delta U + W$ with consistent units (J).",
                "cited_section_ids": [t["sections"][0]["section_id"]]}, i) for i, t in enumerate(topics)]
        drafts = [r for n, r in results if n == "draft_question" and isinstance(r, dict) and "question_id" in r]
        needed = req["practice_exams"] * req["questions_per_exam"]
        verified = {r["question_id"]: r for n, r in results if n == "verify_question" and isinstance(r, dict)
                    and "passed" in r}
        rejected = [qid for qid, r in verified.items() if not r["passed"]]
        replaced = {r.get("replaces") for r in drafts}
        if len([d for d in drafts if not d.get("replaces")]) < needed:
            calls = []
            for i in range(needed):
                t = topics[i % len(topics)]
                calls.append(_call("draft_question", self._question(i // req["questions_per_exam"] + 1, t), i))
            return calls
        pending = [d["question_id"] for d in drafts if d["question_id"] not in verified]
        if pending:
            return [_call("verify_question", {"question_id": q}, i) for i, q in enumerate(pending)]
        to_fix = [q for q in rejected if q not in replaced]
        if to_fix:
            t = topics[0]
            return [_call("draft_question", {**self._question(1, t), "replaces_question_id": q}, i)
                    for i, q in enumerate(to_fix)]
        return [_call("save_exam_pack", {"practice_exams": [
            {"number": n, "title": f"Practice exam {n}", "duration_minutes": 90} for n in range(1, req["practice_exams"] + 1)]})]

    @staticmethod
    def _question(number: int, topic: dict[str, Any]) -> dict[str, Any]:
        return {"practice_exam_number": number, "topic_id": topic["topic_id"],
                "statement_md": "A closed system receives $Q = 500\\,\\text{J}$ of heat and does $W = 200\\,\\text{J}$ "
                                "of work. Compute $\\Delta U$.",
                "solution_md": "$\\Delta U = Q - W = 500 - 200 = 300\\,\\text{J}$.",
                "rubric": [{"criterion": "Applies the first law", "points": 5},
                           {"criterion": "Correct value and units", "points": 5}],
                "points": 10, "cited_section_ids": [topic["sections"][0]["section_id"]]}

    # -- Q&A agent: class history for the date range → answer citing sessions (and a section if found)
    def _qa(self, messages: list[Message]) -> list[dict[str, Any]]:
        goal = str(messages[1]["content"])
        results = _tool_results(messages)
        done = [n for n, _ in results]
        if "get_course_sessions" not in done:
            m = re.search(r"Date range: (\S+) to (\S+)\.", goal)
            args: dict[str, Any] = {}
            if m and m.group(1) != "…":
                args["since"] = m.group(1)
            if m and m.group(2) != "…":
                args["until"] = m.group(2)
            return [_call("get_course_sessions", args)]
        sessions = next(r for n, r in results if n == "get_course_sessions")
        covered = "; ".join(f"{x['date']}: {x['summary'][:60]}" for x in sessions) or "nothing recorded"
        return [_call("answer", {"answer_md": f"In that period you covered: {covered}",
                                 "cited_session_ids": [x["session_id"] for x in sessions]})]

    def _json(self, messages: list[Message]) -> str:
        prompt = " ".join(str(m.get("content", "")) for m in messages)
        if '"certainty"' in prompt:  # timetable vision/text fallback: answer with the fixture's ground truth
            from tests.fixture_factory import TIMETABLE
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            return json.dumps({"slots": [{"subject": sub, "weekday": days[wd], "start": st, "end": en, "room": room,
                                          "professor": prof, "certainty": "certain" if wd != 4 else "unsure"}
                                         for sub, wd, st, en, room, prof in TIMETABLE]})
        if "likely_topics" in prompt:
            ids = re.findall(rf"\[({ID})\]", prompt)
            return json.dumps({"likely_topics": ["First law of thermodynamics"],
                               "summary_md": "The class probably covered the **first law**: $\\Delta U = Q - W$.",
                               "cited_section_ids": ids[:1]})
        if "Intents:" in prompt:
            return json.dumps({"intent": "generate_exam", "course": None, "topic": "first law",
                               "duration_minutes": 30})
        if "solvable_with_given_data" in prompt:
            fail = self.verify_fail_once and len(self._verify_failed) == 0
            if fail:
                self._verify_failed.add("x")
            return json.dumps({"solvable_with_given_data": True, "units_consistent": not fail,
                               "answer_supported_by_notes": True,
                               "issues": ["units of W missing"] if fail else []})
        if "maps_to" in prompt:
            return json.dumps({"is_new_topic": False, "maps_to": "T1"})
        if "title" in prompt:
            return json.dumps({"title": "Class notes topic"})
        return "{}"
