"""The three LLM tool-loop agents: Notes, Course Memory, Exam."""

from __future__ import annotations

from app.agents.base import Tool, ToolLoopAgent
from app.tools.exam import exam_tools
from app.tools.memory import memory_tools
from app.tools.notes import notes_tools


class NotesAgent(ToolLoopAgent):
    name = "notes"
    prompt = "notes_agent"
    task = "notes_structuring"
    max_steps = 16
    require_terminal = True

    def tools(self) -> list[Tool]:
        return notes_tools()


class CourseMemoryAgent(ToolLoopAgent):
    name = "course_memory"
    prompt = "course_memory_agent"
    task = "course_memory"
    max_steps = 12
    require_terminal = True

    def tools(self) -> list[Tool]:
        return memory_tools()


class ExamAgent(ToolLoopAgent):
    name = "exam"
    prompt = "exam_agent"
    task = "exam_generation"
    max_steps = 80
    require_terminal = True

    def tools(self) -> list[Tool]:
        return exam_tools()
