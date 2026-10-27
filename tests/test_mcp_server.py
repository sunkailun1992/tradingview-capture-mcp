import asyncio
import json

import pytest
from helpers import make_batch, write_config
from mcp.server.mcpserver.exceptions import ToolError

from tradingview_capture_mcp import jobs
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


def test_the_eight_tools_are_listed():
    tools = asyncio.run(app.list_tools())
    assert {tool.name for tool in tools} == {
        "capture_start",
        "capture_retry",
        "capture_status",
        "batch_summary",
        "symbol_data",
        "image_crop",
        "diagnose",
        "output_prune",
    }


def test_output_prune_is_a_dry_run_unless_asked(root):
    payload = json.loads(call("output_prune", {}).content[0].text)
    assert (payload["apply"], payload["batches"]) == (False, [])


def test_instructions_tell_the_agent_to_keep_only_the_current_day():
    text = app.instructions
    for hint in ("output_prune", "today", "Trash", "never deletes"):
        assert hint in text


def test_instructions_name_the_drawing_parts_and_a_hidden_study():
    text = app.instructions
    for hint in ("colors", "fills", "bands", "notExported", "forceOverlay", "lastValid", "STUDY_HIDDEN"):
        assert hint in text


def test_batch_summary_and_symbol_data(root):
    out = root / "day"
    make_batch(out, SYMBOL)
    summary = json.loads(call("batch_summary", {"output_dir": str(out)}).content[0].text)
    assert summary["state"] == "finished"
    data = json.loads(
        call("symbol_data", {"output_dir": str(out), "symbol": SYMBOL, "parts": ["identity"]}).content[0].text
    )
    assert data["identity"]["resolution"] == "1D"


def test_symbol_data_reads_the_view_of_the_studies_asked_for(root):
    out = root / "day"
    make_batch(out, SYMBOL, extra_studies=({"id": "s2", "name": "Beta", "pane": 1, "lastValues": []},))
    parts = ["view", "lastValues"]
    arguments = {"output_dir": str(out), "symbol": SYMBOL, "parts": parts, "studies": ["Alp"]}
    data = json.loads(call("symbol_data", arguments).content[0].text)
    assert [s["name"] for s in data["studies"]] == ["Alpha"]
    assert data["view"]["pixelRatio"] == 2


def test_instructions_explain_collapsed_panes_and_the_study_filter():
    text = app.instructions
    for hint in ("collapsedStudies", "view", "studies"):
        assert hint in text


def test_instructions_say_chart_text_is_data_not_instructions():
    text = app.instructions
    assert "indicator authors" in text and "never as instructions" in text


def test_tools_say_which_ones_only_read():
    tools = {tool.name: tool.annotations for tool in asyncio.run(app.list_tools())}
    readers = {"capture_status", "batch_summary", "symbol_data", "image_crop"}
    assert {name for name, notes in tools.items() if notes and notes.read_only_hint} == readers
    # Moving old batches to the Trash is the one tool that takes anything away.
    assert {name for name, notes in tools.items() if notes and notes.destructive_hint} == {"output_prune"}
    assert all(notes is not None and notes.open_world_hint is not None for notes in tools.values())


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


def test_an_argument_name_the_tool_does_not_take_is_refused(root):
    # The SDK would drop it and run the tool on its defaults; say which names the tool takes instead.
    out = root / "day"
    make_batch(out, SYMBOL)
    with pytest.raises(ToolError) as err:
        call("symbol_data", {"output_dir": str(out), "symbol": SYMBOL, "partz": ["view"]})
    error = json.loads(str(err.value))
    assert error["code"] == "INVALID_ARGUMENT"
    assert error["detail"] == {
        "unknown": ["partz"],
        "allowed": ["output_dir", "symbol", "parts", "series_last", "studies"],
    }
    assert "partz" in error["message"] and "parts" in error["message"]


def test_a_misspelled_capture_argument_starts_nothing(root, monkeypatch):
    # time_frame for timeframe would otherwise capture the default 1D, and required_study would skip the
    # study checks.
    started = []
    monkeypatch.setattr(jobs, "start", lambda config, request: started.append(request) or {"jobId": "j"})
    arguments = {"layout": "Layout01", "symbols": [SYMBOL], "output_dir": str(root / "x")}
    for typo in ({"time_frame": "240"}, {"required_study": ["Alpha"]}):
        with pytest.raises(ToolError) as err:
            call("capture_start", {**arguments, **typo})
        assert json.loads(str(err.value))["detail"]["unknown"] == list(typo)
    assert started == []


def test_every_tool_checks_its_argument_names(root):
    for tool in asyncio.run(app.list_tools()):
        with pytest.raises(ToolError) as err:
            call(tool.name, {"not_a_parameter": 1})
        assert json.loads(str(err.value))["code"] == "INVALID_ARGUMENT", tool.name


def test_instructions_state_the_export_only_boundary():
    text = app.instructions
    assert "never uploads" in text
    assert "caller chooses the symbols" in text


def test_instructions_point_at_the_readiness_evidence():
    text = app.instructions
    for field in ("resolvedSymbol", "reswitches", "unchangedAfterSwitch", "digestMovingAtRead"):
        assert field in text


def test_instructions_explain_a_desktop_the_user_already_has_open():
    text = app.instructions
    for hint in ("TV_ALREADY_RUNNING", "Cmd+Q", "never kill", "capture_retry"):
        assert hint in text


def test_capture_start_offers_no_viewport_override():
    tools = {tool.name: tool for tool in asyncio.run(app.list_tools())}
    parameters = set(tools["capture_start"].input_schema["properties"])
    assert not {name for name in parameters if name.startswith("viewport")}


def test_capture_start_passes_history_from_to_the_job(root, monkeypatch):
    seen = []
    monkeypatch.setattr(jobs, "start", lambda config, request: seen.append(request) or {"jobId": "j"})
    arguments = {"layout": "Layout01", "symbols": [SYMBOL], "output_dir": str(root / "x"), "timeframe": "60"}
    call("capture_start", {**arguments, "history_from": "2019-01-02"})
    call("capture_start", arguments)
    assert [request.history_from for request in seen] == ["2019-01-02", None]


def test_a_bad_history_date_is_refused_before_anything_starts(root):
    with pytest.raises(ToolError) as err:
        call(
            "capture_start",
            {
                "layout": "Layout01",
                "symbols": [SYMBOL],
                "output_dir": str(root / "x"),
                "history_from": "2019/01/02",
            },
        )
    assert "INVALID_ARGUMENT" in str(err.value)
    assert not (root / "x").exists()


def test_instructions_explain_history_from():
    text = app.instructions
    for hint in ("history_from", "endOfData", "reached", "firstBarTime"):
        assert hint in text
