"""End-to-end check against a logged-in TradingView Desktop. Local only; private inputs come from the environment."""

import os
from pathlib import Path

import pytest

from tradingview_capture_mcp.capture import CaptureRequest, run_capture
from tradingview_capture_mcp.config import load_config
from tradingview_capture_mcp.driver import RealDesktop
from tradingview_capture_mcp.store import read_json, safe_name

pytestmark = pytest.mark.live


def _env(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


def test_capture_one_symbol_end_to_end():
    if os.environ.get("TRADINGVIEW_CAPTURE_LIVE") != "1":
        pytest.skip("set TRADINGVIEW_CAPTURE_LIVE=1 to run against TradingView Desktop")
    config = load_config()
    layout = _env("TRADINGVIEW_CAPTURE_LIVE_LAYOUT")
    symbol = _env("TRADINGVIEW_CAPTURE_LIVE_SYMBOL")
    studies = tuple(s for s in os.environ.get("TRADINGVIEW_CAPTURE_LIVE_STUDIES", "").split(",") if s)
    out = Path(_env("TRADINGVIEW_CAPTURE_LIVE_PARENT")) / f"live-{os.getpid()}"
    request = CaptureRequest(
        layout=layout, symbols=(symbol,), timeframe="1D", output_dir=str(out), required_studies=studies
    )
    summary = run_capture(
        request, config, job_id="f" * 32, desktop=RealDesktop(config, layout), pid=os.getpid()
    )
    assert summary["state"] == "finished", summary
    assert summary["totals"]["succeeded"] == 1, summary
    folder = out / "raw" / safe_name(symbol)
    data = read_json(folder / "data.json")
    assert data["identity"]["symbol"] == symbol
    assert any(study["tables"] for study in data["studies"])
    assert (folder / "chart.csv").read_text(encoding="utf-8").startswith("time,open,high,low,close")
