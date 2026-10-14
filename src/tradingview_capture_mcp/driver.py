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


class RealDesktop:
    """Starts the installed TradingView Desktop and connects to one layout's tab."""

    def __init__(self, config: Config, layout: str, *, page_timeout: float = 60.0) -> None:
        self._config = config
        self._layout = layout
        self._page_timeout = page_timeout
        self._session: desktop.DesktopSession | None = None
        self._cdp: cdp.CdpSession | None = None

    def start(self) -> tuple[DesktopInfo, ChartDriver]:
        self._session = desktop.launch(self._config)
        target = desktop.wait_for_chart_page(
            self._config.debug_port, self._layout, timeout=self._page_timeout
        )
        self._cdp = cdp.CdpSession(target["webSocketDebuggerUrl"])
        driver = CdpDriver(self._cdp)
        _wait_for_chart_api(driver, self._page_timeout)
        return DesktopInfo(version=self._session.version, browser=self._session.browser), driver

    def stop(self) -> None:
        if self._cdp is not None:
            with contextlib.suppress(Exception):
                self._cdp.close()
            self._cdp = None
        if self._session is not None:
            desktop.stop_process(self._session.process)
            self._session = None


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
