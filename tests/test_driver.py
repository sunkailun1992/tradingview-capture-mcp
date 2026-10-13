import pytest

from tradingview_capture_mcp import driver as driver_module
from tradingview_capture_mcp.driver import CdpDriver, Viewport, _wait_for_chart_api
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


def test_run_sends_the_built_page_script():
    session = FakeSession([{"api": "object"}])
    assert CdpDriver(session).run("alive", timeout=7) == {"api": "object"}
    assert "typeof window.TradingViewApi" in session.calls[0][1]
    assert session.calls[0][2] == 7


def test_viewport_override_and_reset():
    session = FakeSession()
    chart = CdpDriver(session)
    chart.set_viewport(Viewport(800, 600, 2.0))
    chart.clear_viewport()
    assert session.calls == [
        (
            "call",
            "Emulation.setDeviceMetricsOverride",
            {"width": 800, "height": 600, "deviceScaleFactor": 2.0, "mobile": False},
        ),
        ("call", "Emulation.clearDeviceMetricsOverride", None),
    ]


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
