from pathlib import Path

import pytest

from tradingview_capture_mcp import desktop
from tradingview_capture_mcp import driver as driver_module
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.driver import CdpDriver, RealDesktop, _wait_for_chart_api
from tradingview_capture_mcp.errors import CaptureError


class FakeSession:
    def __init__(self, values=None):
        self.calls = []
        self.values = list(values or [])

    def evaluate(self, expression, *, timeout=60.0):
        self.calls.append(("evaluate", expression, timeout))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def call(self, method, params=None, *, timeout=60.0):
        self.calls.append(("call", method, params))
        return {}

    def close(self):
        self.calls.append(("close",))


def test_run_sends_the_built_page_script():
    session = FakeSession([{"api": "object"}])
    assert CdpDriver(session).run("alive", timeout=7) == {"api": "object"}
    assert "typeof window.TradingViewApi" in session.calls[0][1]
    assert session.calls[0][2] == 7


def test_wait_for_chart_api_retries_while_the_page_loads(monkeypatch):
    monkeypatch.setattr(driver_module.time, "sleep", lambda seconds: None)
    session = FakeSession(
        [
            CaptureError("CDP_ERROR", "not yet"),
            {"api": "undefined", "symbol": None},
            {"api": "object", "symbol": "BINANCE:BTCUSDT.P"},
        ]
    )
    _wait_for_chart_api(CdpDriver(session), timeout=30)
    assert len(session.calls) == 3


def test_wait_for_chart_api_gives_up():
    session = FakeSession([{"api": "undefined", "symbol": None}])
    with pytest.raises(CaptureError) as err:
        _wait_for_chart_api(CdpDriver(session), timeout=0)
    assert err.value.code == "TV_INTERNALS_CHANGED"


@pytest.mark.parametrize(
    "launched, process, left_open", [(False, None, True), (True, None, True), (True, "p", False)]
)
def test_a_real_desktop_says_how_it_got_tradingview_and_lets_go_of_it(
    monkeypatch, launched, process, left_open
):
    session = desktop.DesktopSession(
        port=9333, version="9.9.9", browser="Chrome/1", pid=77, launched=launched, process=process
    )
    page = FakeSession([{"api": "object", "symbol": "BINANCE:AAAUSDT.P"}])
    released = []
    monkeypatch.setattr(desktop, "connect_or_launch", lambda config: session)
    monkeypatch.setattr(
        desktop, "wait_for_chart_page", lambda port, layout, timeout=60.0: {"webSocketDebuggerUrl": "ws://x"}
    )
    monkeypatch.setattr(desktop, "release", released.append)
    monkeypatch.setattr(driver_module.cdp, "CdpSession", lambda url: page)
    config = Config(app_path=Path("/nonexistent/TradingView.app"), debug_port=9333, output_root=Path("/tmp"))
    real = RealDesktop(config, "Layout01")
    info, _ = real.start()
    assert (info.version, info.launched, info.left_open) == ("9.9.9", launched, left_open)
    real.stop()
    real.stop()  # a second stop, as the signal handler may do, lets go only once
    assert released == [session]
    assert page.calls[-1] == ("close",)
