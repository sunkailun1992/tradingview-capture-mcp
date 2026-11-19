"""Seams between the capture flow and TradingView Desktop, with the real implementations."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import Any, Protocol

from . import cdp, desktop, page
from .config import Config
from .errors import CDP_ERROR, TV_INTERNALS_CHANGED, CaptureError


@dataclass(frozen=True)
class DesktopInfo:
    version: str
    browser: str
    launched: bool = False  # this batch started TradingView Desktop; otherwise it was already open
    left_open: bool = True  # TradingView Desktop keeps running when the batch ends


class ChartDriver(Protocol):
    def run(self, script: str, args: dict[str, Any] | None = None, *, timeout: float = 60.0) -> Any: ...


class DesktopControl(Protocol):
    def start(self) -> tuple[DesktopInfo, ChartDriver]: ...

    def stop(self) -> None: ...


class CdpDriver:
    """Runs the fixed page scripts in one chart tab."""

    def __init__(self, session: cdp.CdpSession) -> None:
        self._session = session

    def run(self, script: str, args: dict[str, Any] | None = None, *, timeout: float = 60.0) -> Any:
        return self._session.evaluate(page.build(script, args), timeout=timeout)


# Desktops in use by this process, so a termination signal can let go of them from any thread.
_ACTIVE: set[Any] = set()


def stop_all_desktops() -> None:
    for desktop_control in list(_ACTIVE):
        with contextlib.suppress(Exception):
            desktop_control.stop()


class RealDesktop:
    """Uses the TradingView Desktop that runs with the debugging port, or starts it, and connects to one
    layout's tab. It quits TradingView only when it started it and the config says not to keep it open."""

    def __init__(self, config: Config, layout: str, *, page_timeout: float = 60.0) -> None:
        self._config = config
        self._layout = layout
        self._page_timeout = page_timeout
        self._session: desktop.DesktopSession | None = None
        self._cdp: cdp.CdpSession | None = None

    def start(self) -> tuple[DesktopInfo, ChartDriver]:
        self._session = session = desktop.connect_or_launch(self._config)
        _ACTIVE.add(self)
        target = desktop.wait_for_chart_page(
            self._config.debug_port, self._layout, timeout=self._page_timeout
        )
        self._cdp = cdp.CdpSession(target["webSocketDebuggerUrl"])
        driver = CdpDriver(self._cdp)
        _wait_for_chart_api(driver, self._page_timeout)
        info = DesktopInfo(
            version=session.version,
            browser=session.browser,
            launched=session.launched,
            left_open=session.process is None,
        )
        return info, driver

    def stop(self) -> None:
        if self._cdp is not None:
            with contextlib.suppress(Exception):
                self._cdp.close()
            self._cdp = None
        if self._session is not None:
            session, self._session = self._session, None
            desktop.release(session)
        _ACTIVE.discard(self)


def _wait_for_chart_api(driver: ChartDriver, timeout: float) -> None:
    """The tab exists before TradingView's chart API does; poll until a symbol is loaded."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            state: Any = driver.run("alive", timeout=10.0)
            if isinstance(state, dict) and state.get("api") == "object" and state.get("symbol"):
                return
        except CaptureError as exc:
            if exc.code != CDP_ERROR:
                raise
            state = {"error": exc.message}
        if time.monotonic() >= deadline:
            raise CaptureError(
                TV_INTERNALS_CHANGED, "the chart API did not become available", {"state": state}
            )
        time.sleep(1.0)
