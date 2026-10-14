"""Turn SIGTERM and SIGHUP into SystemExit so cleanup runs: the chart is restored and TradingView stops."""

from __future__ import annotations

import contextlib
import signal
from collections.abc import Iterator
from types import FrameType

from .driver import stop_all_desktops

TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


def _ignore_further_signals() -> None:
    # A second signal must not interrupt the cleanup the first one started.
    for sig in TERMINATION_SIGNALS:
        signal.signal(sig, signal.SIG_IGN)


def _raise_exit(signum: int, frame: FrameType | None) -> None:
    _ignore_further_signals()
    raise SystemExit(128 + signum)


@contextlib.contextmanager
def exit_on_termination() -> Iterator[None]:
    """For commands that run a batch or a doctor check in this process."""
    previous = {sig: signal.signal(sig, _raise_exit) for sig in TERMINATION_SIGNALS}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def install_server_handlers() -> None:
    """For the long-running MCP server: a tool may be running TradingView in another thread."""

    def handler(signum: int, frame: FrameType | None) -> None:
        _ignore_further_signals()
        stop_all_desktops()
        raise SystemExit(128 + signum)

    for sig in TERMINATION_SIGNALS:
        signal.signal(sig, handler)
