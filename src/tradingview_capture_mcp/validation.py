"""Input formats accepted from callers."""

from __future__ import annotations

import re

from .errors import INVALID_ARGUMENT, CaptureError

LAYOUT_RE = re.compile(r"[A-Za-z0-9]{4,32}")
SYMBOL_RE = re.compile(r"[A-Z0-9_]{1,32}:[A-Za-z0-9._!&-]{1,64}")
TIMEFRAME_RE = re.compile(r"[1-9][0-9]{0,3}[SDWM]?|[DWM]")


def check_layout(layout: str) -> str:
    if not isinstance(layout, str) or not LAYOUT_RE.fullmatch(layout):
        raise CaptureError(
            INVALID_ARGUMENT, "layout must be 4-32 letters or digits", {"layout": str(layout)[:64]}
        )
    return layout
