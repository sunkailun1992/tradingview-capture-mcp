import asyncio
import json

import pytest
from helpers import make_batch, write_config
from mcp.server.mcpserver.exceptions import ToolError

from tradingview_capture_mcp.mcp_server import app

SYMBOL = "BINANCE:AAAUSDT.P"


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("TRADINGVIEW_CAPTURE_CONFIG", str(write_config(tmp_path, root)))
    return root.resolve()


def call(name, arguments):
    return asyncio.run(app.call_tool(name, arguments))


def test_the_seven_tools_are_listed():
    tools = asyncio.run(app.list_tools())
    assert {tool.name for tool in tools} == {
        "capture_start",
        "capture_retry",
        "capture_status",
        "batch_summary",
        "symbol_data",
        "image_crop",
        "diagnose",
    }


def test_batch_summary_and_symbol_data(root):
    out = root / "day"
    make_batch(out, SYMBOL)
    summary = json.loads(call("batch_summary", {"output_dir": str(out)}).content[0].text)
    assert summary["state"] == "finished"
    data = json.loads(
        call("symbol_data", {"output_dir": str(out), "symbol": SYMBOL, "parts": ["identity"]}).content[0].text
    )
    assert data["identity"]["resolution"] == "1D"


def test_image_crop_returns_an_image(root):
    out = root / "day"
    make_batch(out, SYMBOL)
    result = call(
        "image_crop", {"output_dir": str(out), "symbol": SYMBOL, "x": 0, "y": 0, "width": 8, "height": 8}
    )
    assert (result.content[0].type, result.content[0].mime_type) == ("image", "image/png")


def test_errors_carry_the_code(root):
    with pytest.raises(ToolError) as err:
        call("capture_start", {"layout": "../bad", "symbols": [SYMBOL], "output_dir": str(root / "x")})
    assert "INVALID_ARGUMENT" in str(err.value)
    with pytest.raises(ToolError) as err:
        call("capture_status", {"job_id": "c" * 32})
    assert "NOT_FOUND" in str(err.value)


def test_instructions_state_the_export_only_boundary():
    text = app.instructions
    assert "never uploads" in text
    assert "caller chooses the symbols" in text
