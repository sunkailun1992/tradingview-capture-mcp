"""Load older bars into the chart before it is read, when the caller asks for history from a date."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .errors import NOT_READY_TIMEOUT, SYMBOL_NOT_FOUND, CaptureError
from .validation import same_symbol

# Older bars asked for at once; TradingView Desktop 3.4.1 sent 5000 in one answer within seconds (2026-10-15).
MAX_REQUEST = 5000
# 11/10: 10% more than the loaded bars' spacing predicts, for holidays and shorter sessions further back.
MARGIN = (11, 10)


@dataclass(frozen=True)
class HistoryState:
    """The main series' loaded bars as the history script reports them."""

    symbol: str
    resolution: str
    bars: int
    first_bar_time: int | None
    last_bar_time: int | None
    loading: bool
    can_request: bool
    # TradingView's data_completed flag of the last answer, e.g. "limit": the server sends no older bars.
    end_of_data: str | None
    requested: int

    @classmethod
    def from_page(cls, raw: dict[str, Any]) -> HistoryState:
        end = raw.get("endOfData")
        return cls(
            symbol=str(raw.get("symbol") or ""),
            resolution=str(raw.get("resolution") or ""),
            bars=int(raw.get("bars") or 0),
            first_bar_time=raw.get("firstBarTime"),
            last_bar_time=raw.get("lastBarTime"),
            loading=bool(raw.get("loading")),
            can_request=bool(raw.get("canRequest")),
            end_of_data=None if end is None else str(end),
            requested=int(raw.get("requested") or 0),
        )

    def reached(self, target: int) -> bool:
        return self.first_bar_time is not None and self.first_bar_time <= target

    def done(self, target: int) -> bool:
        """Nothing left to ask for: the target is loaded, or TradingView sends nothing older."""
        return self.reached(target) or self.end_of_data is not None

    def loaded(self) -> tuple[Any, ...]:
        """What an answer to a request changes. New bars at the end (an open market) leave it as it is."""
        return (self.first_bar_time, self.end_of_data)


def request_size(state: HistoryState, target: int) -> int:
    """Older bars to ask for: the gap to `target` at the loaded bars' average spacing, plus a margin."""
    if state.reached(target):
        return 0
    first, last = state.first_bar_time, state.last_bar_time
    span = int(last - first) if first is not None and last is not None else 0
    if state.bars < 2 or span <= 0:
        return MAX_REQUEST
    # gap / spacing * margin in whole numbers, rounded up, so 110.00000000000001 never becomes 111.
    numerator = int(first - target) * (state.bars - 1) * MARGIN[0]
    return max(1, min(MAX_REQUEST, -(-numerator // (span * MARGIN[1]))))


@dataclass(frozen=True)
class HistoryLoad:
    before: HistoryState
    after: HistoryState
    requests: int
    waited: float


def load_history(
    run: Callable[[int], HistoryState],
    *,
    symbol: str,
    target: int,
    timeout: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    interval: float = 1.0,
) -> HistoryLoad:
    """Ask for older bars until the first bar is at or before `target` or TradingView sends nothing older,
    then wait until two reads show the same first bar. `run(n)` runs the history script, which asks for
    n older bars if n > 0.

    The series takes one request at a time, so one goes out only while it is idle. The waiting happens here
    rather than in the page because a hidden TradingView window can hold its timers back for many seconds."""
    start = clock()
    before: HistoryState | None = None
    previous: HistoryState | None = None
    requests = 0
    while True:
        state = run(0)
        if before is None:
            before = state
        if not same_symbol(state.symbol, symbol):
            raise CaptureError(
                SYMBOL_NOT_FOUND, "the chart left this symbol while loading history", {"symbol": state.symbol}
            )
        elapsed = clock() - start
        if not state.done(target):
            previous = None
            if not state.loading and state.can_request and run(request_size(state, target)).requested:
                requests += 1
        elif state.loading:
            previous = None
        elif previous is not None and previous.loaded() == state.loaded():
            return HistoryLoad(before, state, requests, elapsed)
        else:
            previous = state
        if elapsed >= timeout:
            raise CaptureError(
                NOT_READY_TIMEOUT,
                f"the chart did not finish loading history within {timeout:g}s",
                {
                    "reason": "history",
                    "symbol": state.symbol,
                    "requests": requests,
                    "barsCount": state.bars,
                    "firstBarTime": state.first_bar_time,
                },
            )
        sleep(interval)
