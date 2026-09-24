from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


class TextPart(TypedDict):
    type: Literal["text"]
    text: str


class ImagePart(TypedDict):
    type: Literal["image"]
    media_type: str
    data: str  # base64


class ToolCall(TypedDict, total=False):
    id: str
    name: str
    arguments: dict[str, Any]
    arguments_error: str  # set when the provider returned unparseable JSON arguments
    extra: dict[str, Any]  # provider-specific fields that must be echoed back (e.g. Gemini thought signatures)


class Message(TypedDict, total=False):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[TextPart | ImagePart]
    tool_calls: list[ToolCall]
    tool_call_id: str
    name: str


class ToolSpec(TypedDict):
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    input_tokens: int
    output_tokens: int
    provider: str
    model: str
    finish_reason: str = ""
    cost_usd: float = 0.0
    latency_ms: int = 0
    is_fallback: bool = False
    raw_usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallContext:
    user_id: str
    agent_run_id: str | None = None
    # When set, the call log is written through (and committed on) this user-scoped session, so an
    # agent's open transaction never blocks the logger on SQLite's single-writer lock.
    session: Any = None


class LLMError(RuntimeError):
    def __init__(self, provider: str, model: str, message: str, status: int | None = None):
        super().__init__(f"{provider}/{model}: {message}")
        self.provider, self.model, self.status = provider, model, status


class LLMUnavailable(RuntimeError):
    """Every model in the task's chain failed."""

    def __init__(self, task: str, errors: list[str]):
        super().__init__(f"No model available for task '{task}': " + " | ".join(errors))
        self.task, self.errors = task, errors
