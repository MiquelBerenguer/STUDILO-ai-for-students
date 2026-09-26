"""The student journey as explicit state machines.

Journey (per user):        onboarding ──complete_setup──▶ active
ClassSession (per class):  scheduled ─▶ awaiting_upload ─▶ uploaded ─▶ processed
                                             └──▶ missed ──(late upload)──▶ uploaded
Upload (per file):         received ─▶ extracting ─▶ classifying ─▶ structuring ─▶ updating_memory ─▶ done
                           (past exams: classifying ─▶ done)       any non-terminal ─▶ failed ─(retry)─▶ received
ExamPack (per build):      pending ─▶ building ─▶ ready | failed
Card (feed):               open ─▶ done | dismissed
AgentAction (UX §7):       proposed ─▶ applied | rejected ; applied ─▶ undone
Job (orchestrator):        queued ─▶ running ─▶ succeeded | failed ; failed ─(retry)─▶ queued

Every state change in the code base goes through `transition()`, which rejects illegal moves.
"""

from __future__ import annotations

from typing import Protocol


class IllegalTransition(ValueError):
    pass


class StateMachine:
    def __init__(self, name: str, transitions: dict[str, set[str]]):
        self.name = name
        self.transitions = transitions
        self.states = set(transitions) | {s for v in transitions.values() for s in v}

    def can(self, src: str, dst: str) -> bool:
        return dst in self.transitions.get(src, set())

    def check(self, src: str, dst: str) -> None:
        if not self.can(src, dst):
            raise IllegalTransition(f"{self.name}: illegal transition {src!r} -> {dst!r}")


JOURNEY = StateMachine("journey", {"onboarding": {"active"}, "active": set()})

CLASS_SESSION = StateMachine("class_session", {
    "scheduled": {"awaiting_upload", "uploaded"},
    "awaiting_upload": {"uploaded", "missed"},
    "missed": {"uploaded"},
    "uploaded": {"processed", "uploaded", "scheduled", "awaiting_upload", "missed"},  # last three: undo
    "processed": {"uploaded", "scheduled", "awaiting_upload", "missed"},  # another upload, or undo
})

UPLOAD = StateMachine("upload", {
    "received": {"extracting", "failed"},
    "extracting": {"classifying", "failed"},
    "classifying": {"structuring", "done", "failed"},
    "structuring": {"updating_memory", "failed"},
    "updating_memory": {"done", "failed"},
    "failed": {"received"},
    "done": {"undone"},  # the student undid the autonomous filing
    "undone": set(),
})

EXAM_PACK = StateMachine("exam_pack", {
    "pending": {"building", "failed"},
    "building": {"ready", "failed"},
    "ready": set(),
    "failed": set(),
})

CARD = StateMachine("card", {"open": {"done", "dismissed"}, "done": set(), "dismissed": set()})

ACTION = StateMachine("agent_action", {
    "proposed": {"applied", "rejected"},
    "applied": {"undone"},
    "rejected": set(),
    "undone": set(),
})

JOB = StateMachine("job", {
    "queued": {"running", "failed"},
    "running": {"succeeded", "failed", "queued"},
    "failed": {"queued"},
    "succeeded": set(),
})


class _HasState(Protocol):
    state: str


def transition(machine: StateMachine, obj: _HasState | object, dst: str, attr: str = "state") -> None:
    """Move `obj.<attr>` to `dst`, rejecting illegal moves. Cards and agent actions use attr="status"."""
    machine.check(getattr(obj, attr), dst)
    setattr(obj, attr, dst)
