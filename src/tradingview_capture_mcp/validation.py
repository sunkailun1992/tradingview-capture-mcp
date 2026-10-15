"""Input formats accepted from callers."""

from __future__ import annotations

import calendar
import datetime as dt
import re

from .errors import INVALID_ARGUMENT, CaptureError

LAYOUT_RE = re.compile(r"[A-Za-z0-9]{4,32}")
SYMBOL_RE = re.compile(r"[A-Z0-9_]{1,32}:[A-Za-z0-9._!&-]{1,64}")
TIMEFRAME_RE = re.compile(r"[1-9][0-9]{0,3}[SDWM]?|[DWM]")
HISTORY_FROM_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# TradingView's own "scroll to the first bar" asks for 1800-01-01; nothing older can exist on a chart.
EARLIEST_HISTORY_YEAR = 1800


def check_layout(layout: str) -> str:
    if not isinstance(layout, str) or not LAYOUT_RE.fullmatch(layout):
        raise CaptureError(
            INVALID_ARGUMENT, "layout must be 4-32 letters or digits", {"layout": str(layout)[:64]}
        )
    return layout


def history_from_time(value: str) -> int:
    """UNIX seconds of 00:00 UTC on a YYYY-MM-DD date, the time bars in chart.csv are compared with."""
    bad = CaptureError(
        INVALID_ARGUMENT,
        f"history_from must be a date written YYYY-MM-DD, {EARLIEST_HISTORY_YEAR}-01-01 or later",
        {"history_from": str(value)[:32]},
    )
    if not isinstance(value, str) or not HISTORY_FROM_RE.fullmatch(value):
        raise bad
    try:
        day = dt.date.fromisoformat(value)
    except ValueError:
        raise bad from None
    if day.year < EARLIEST_HISTORY_YEAR:
        raise bad
    return calendar.timegm(day.timetuple())


# TradingView serves symbols without a real-time subscription under a delayed-feed exchange name.
DELAYED_FEED_SUFFIXES = ("_DL", "_DLY")


def same_symbol(actual: str, requested: str) -> bool:
    """True when the chart shows the requested code, directly or from its delayed feed."""
    if not actual:
        return False
    if actual == requested:
        return True
    actual_exchange, _, actual_ticker = actual.partition(":")
    requested_exchange, _, requested_ticker = requested.partition(":")
    return actual_ticker == requested_ticker and any(
        actual_exchange == requested_exchange + suffix for suffix in DELAYED_FEED_SUFFIXES
    )
