"""Decide when a freshly switched chart is safe to read."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .errors import NOT_READY_TIMEOUT, CaptureError

STATUS_COMPLETED = 2


@dataclass(frozen=True)
class StudyState:
    id: str
    name: str
    status: int | None
    last_time: int | None
    digest: str


@dataclass(frozen=True)
class ReadySnapshot:
    symbol: str
    resolution: str
    last_bar_time: int | None
    studies: tuple[StudyState, ...]

    @classmethod
    def from_page(cls, raw: dict[str, Any]) -> ReadySnapshot:
        return cls(
            symbol=str(raw.get("symbol") or ""),
            resolution=str(raw.get("resolution") or ""),
            last_bar_time=raw.get("lastBarTime"),
            studies=tuple(
                StudyState(
                    id=str(s.get("id") or ""),
                    name=str(s.get("name") or ""),
                    status=s.get("status"),
                    last_time=s.get("lastTime"),
                    digest=hashlib.sha256(str(s.get("digest")).encode("utf-8")).hexdigest(),
                )
                for s in raw.get("studies") or []
            ),
        )


@dataclass(frozen=True)
class ReadyVerdict:
    ready: bool
    reason: str | None
    unchanged: tuple[str, ...] = ()


def normalize_resolution(value: str) -> str:
    upper = value.strip().upper()
    return "1" + upper if upper in {"D", "W", "M"} else upper


def judge(
    *,
    target: str,
    timeframe: str,
    current: ReadySnapshot,
    previous: ReadySnapshot | None,
    before_switch: ReadySnapshot | None,
    elapsed: float,
    grace_sec: float = 10.0,
) -> ReadyVerdict:
    """Ready means: right symbol and resolution, every study finished on the last bar, two equal reads,
    and the studies' output differs from the previous symbol's (or the grace period has passed)."""
    if current.symbol != target:
        return ReadyVerdict(False, "symbol")
    if normalize_resolution(current.resolution) != normalize_resolution(timeframe):
        return ReadyVerdict(False, "resolution")
    if current.last_bar_time is None:
        return ReadyVerdict(False, "bars")
    for study in current.studies:
        if study.status is not None and study.status != STATUS_COMPLETED:
            return ReadyVerdict(False, f"status:{study.name}")
        if study.last_time != current.last_bar_time:
            return ReadyVerdict(False, f"lastTime:{study.name}")
    if previous != current:
        return ReadyVerdict(False, "unstable")
    unchanged: tuple[str, ...] = ()
    if before_switch is not None and before_switch.symbol != target:
        old = {s.id: s.digest for s in before_switch.studies}
        unchanged = tuple(s.name for s in current.studies if old.get(s.id) == s.digest)
        if unchanged and elapsed < grace_sec:
            return ReadyVerdict(False, f"unchanged:{unchanged[0]}", unchanged)
    return ReadyVerdict(True, None, unchanged)


def wait_until_ready(
    read: Callable[[], ReadySnapshot],
    *,
    target: str,
    timeframe: str,
    before_switch: ReadySnapshot | None,
    timeout: float,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    interval: float = 1.0,
    grace_sec: float = 10.0,
) -> tuple[ReadyVerdict, ReadySnapshot, int, float]:
    start = clock()
    previous: ReadySnapshot | None = None
    polls = 0
    while True:
        current = read()
        polls += 1
        elapsed = clock() - start
        verdict = judge(
            target=target,
            timeframe=timeframe,
            current=current,
            previous=previous,
            before_switch=before_switch,
            elapsed=elapsed,
            grace_sec=grace_sec,
        )
        if verdict.ready:
            return verdict, current, polls, elapsed
        if elapsed >= timeout:
            raise CaptureError(
                NOT_READY_TIMEOUT,
                f"the chart was not ready after {timeout:g}s",
                {"reason": verdict.reason, "polls": polls},
            )
        previous = current
        sleep(interval)
