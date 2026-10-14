"""Error codes shared by the command line, the MCP tools and the capture process."""

from __future__ import annotations

from typing import Any

TV_NOT_INSTALLED = "TV_NOT_INSTALLED"
TV_ALREADY_RUNNING = "TV_ALREADY_RUNNING"
TV_STARTUP_TIMEOUT = "TV_STARTUP_TIMEOUT"
PORT_IN_USE = "PORT_IN_USE"
CDP_NOT_LOCAL = "CDP_NOT_LOCAL"
CDP_ERROR = "CDP_ERROR"
LAYOUT_NOT_FOUND = "LAYOUT_NOT_FOUND"
LAYOUT_NOT_UNIQUE = "LAYOUT_NOT_UNIQUE"
TV_INTERNALS_CHANGED = "TV_INTERNALS_CHANGED"
SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
NOT_READY_TIMEOUT = "NOT_READY_TIMEOUT"
STUDY_MISSING = "STUDY_MISSING"
STUDY_HIDDEN = "STUDY_HIDDEN"
OUTPUT_EXISTS = "OUTPUT_EXISTS"
OUTPUT_OUTSIDE_ROOT = "OUTPUT_OUTSIDE_ROOT"
BATCH_LOCKED = "BATCH_LOCKED"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
CONFIG_INVALID = "CONFIG_INVALID"
NOT_FOUND = "NOT_FOUND"
INTERNAL_ERROR = "INTERNAL_ERROR"
INTERRUPTED = "INTERRUPTED"
TRASH_UNAVAILABLE = "TRASH_UNAVAILABLE"
TRASH_FAILED = "TRASH_FAILED"


class CaptureError(Exception):
    """A failure with a stable code that callers and agents can act on."""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}
