import dataclasses
import json
import stat

import pytest
from fakes import OK_DIAGNOSE, FakeChart, FakeClock, FakeDesktop

from tradingview_capture_mcp.capture import CaptureRequest, run_capture, validate_request
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.driver import Viewport
from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.store import BatchLock, read_json, safe_name, sha256_bytes, write_json_new

SYMBOLS = ("BINANCE:AAAUSDT.P", "BINANCE:BBBUSDT.P", "NYMEX:CL1!")


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=root.resolve())


def make_request(config, **changes):
    base = CaptureRequest(
        layout="Layout01",
        symbols=SYMBOLS,
        timeframe="1D",
        output_dir=str(config.output_root / "batch"),
        required_studies=("Alpha",),
        viewport=Viewport(800, 600, 2.0),
    )
    return dataclasses.replace(base, **changes)


def capture(config, request, chart=None, **desktop_options):
    chart = chart or FakeChart()
    desktop = FakeDesktop(chart, **desktop_options)
    clock = FakeClock()
    summary = run_capture(
        request, config, job_id="a" * 32, desktop=desktop, pid=4242, sleep=clock.sleep, clock=clock
    )
    return summary, chart, desktop


def test_captures_every_symbol_and_restores_the_chart(config):
    summary, chart, desktop = capture(config, make_request(config))
    out = config.output_root / "batch"
    assert summary["state"] == "finished"
    assert summary["totals"] == {"requested": 3, "succeeded": 3, "failed": 0, "pending": 0}
    assert (desktop.started, desktop.stopped) == (1, 1)
    assert (chart.symbol, chart.viewport) == ("SSE_DLY:000001", None)
    for code in SYMBOLS:
        folder = out / "raw" / safe_name(code)
        for name in ("image.png", "chart.csv", "data.json", "capture.json"):
            assert stat.S_IMODE((folder / name).stat().st_mode) == 0o600
        record = read_json(folder / "capture.json")
        assert (record["symbol"], record["captureMethod"], record["desktop"]["version"]) == (
            code,
            "CDP_DESKTOP",
            "3.4.1",
        )
        assert record["files"]["chart.csv"]["sha256"] == sha256_bytes((folder / "chart.csv").read_bytes())
        assert record["files"]["image.png"]["width"] == 40
    data = read_json(out / "raw" / safe_name(SYMBOLS[0]) / "data.json")
    assert data["readiness"]["polls"] >= 2
    assert data["readiness"]["unchangedAfterSwitch"] == []
    manifest = read_json(out / "capture-manifest.json")
    assert (manifest["state"], manifest["desktopVersionChanged"], manifest["attempts"]) == (
        "finished",
        False,
        1,
    )
    job = read_json(out / "job.json")
    assert (job["state"], job["succeeded"], job["pid"]) == ("finished", 3, 4242)
    assert read_json(out / "batch.json")["request"]["symbols"] == list(SYMBOLS)
    assert [p.name for p in (out / "raw").iterdir() if p.name.startswith(".")] == []


def test_stops_before_any_symbol_when_the_internals_changed(config):
    broken = json.loads(json.dumps(OK_DIAGNOSE))
    broken["checks"][0] = {"name": "activeChart", "ok": False, "error": "gone"}
    summary, _, desktop = capture(config, make_request(config), FakeChart(diagnose=broken))
    out = config.output_root / "batch"
    assert (summary["state"], summary["error"]["code"]) == ("stopped", "TV_INTERNALS_CHANGED")
    assert summary["error"]["detail"]["failedChecks"] == ["activeChart"]
    assert summary["totals"]["pending"] == 3
    assert list((out / "raw").iterdir()) == []
    assert desktop.stopped == 1
    assert read_json(out / "job.json")["state"] == "failed"


def test_the_self_check_stops_the_batch_when_the_first_symbol_lacks_a_required_study(config):
    chart = FakeChart(missing_study=(SYMBOLS[0], "Alpha"))
    summary, _, _ = capture(config, make_request(config), chart)
    assert summary["state"] == "stopped"
    assert summary["error"]["detail"]["failedChecks"] == ["requiredStudies"]
    assert chart.symbol == "SSE_DLY:000001"


def test_later_failures_are_recorded_and_the_batch_goes_on(config):
    chart = FakeChart(missing_study=(SYMBOLS[1], "Alpha"), never_ready={SYMBOLS[2]})
    summary, _, _ = capture(config, make_request(config), chart)
    assert summary["state"] == "finished"
    assert summary["totals"] == {"requested": 3, "succeeded": 1, "failed": 2, "pending": 0}
    assert [(f["symbol"], f["code"]) for f in summary["failures"]] == [
        (SYMBOLS[1], "STUDY_MISSING"),
        (SYMBOLS[2], "NOT_READY_TIMEOUT"),
    ]
    assert not (config.output_root / "batch" / "raw" / safe_name(SYMBOLS[1])).exists()


def test_an_unknown_symbol_fails_alone(config):
    summary, _, _ = capture(config, make_request(config), FakeChart(unknown={SYMBOLS[1]}))
    assert [(f["symbol"], f["code"]) for f in summary["failures"]] == [(SYMBOLS[1], "SYMBOL_NOT_FOUND")]
    assert summary["totals"]["succeeded"] == 2


def test_output_that_looks_unchanged_is_accepted_after_the_grace_period(config):
    summary, _, _ = capture(config, make_request(config, symbols=SYMBOLS[:1]), FakeChart(static_study="Beta"))
    data = read_json(config.output_root / "batch" / "raw" / safe_name(SYMBOLS[0]) / "data.json")
    assert summary["state"] == "finished"
    assert data["readiness"]["unchangedAfterSwitch"] == ["Beta"]
    assert data["readiness"]["waitedSec"] >= 10


def test_retry_runs_only_failed_symbols_and_keeps_earlier_files(config):
    chart = FakeChart(unknown={SYMBOLS[1]})
    capture(config, make_request(config), chart)
    out = config.output_root / "batch"
    first = (out / "raw" / safe_name(SYMBOLS[0]) / "capture.json").read_bytes()
    chart.unknown.clear()
    chart.calls.clear()
    summary, _, _ = capture(config, make_request(config, retry_failed=True), chart)
    assert summary["totals"]["succeeded"] == 3
    assert read_json(out / "capture-manifest.json")["attempts"] == 2
    assert read_json(out / "attempts" / "2" / "attempt.json")["symbols"] == [SYMBOLS[1]]
    assert (out / "raw" / safe_name(SYMBOLS[0]) / "capture.json").read_bytes() == first
    assert [args["symbol"] for script, args in chart.calls if script == "switch"] == [
        SYMBOLS[1],
        "SSE_DLY:000001",
    ]


def test_retry_with_nothing_left_to_do(config):
    capture(config, make_request(config))
    with pytest.raises(CaptureError) as err:
        capture(config, make_request(config, retry_failed=True))
    assert err.value.code == "NOT_FOUND"


def test_refuses_an_existing_output_dir_and_a_held_lock(config):
    (config.output_root / "batch").mkdir()
    with pytest.raises(CaptureError) as err:
        capture(config, make_request(config))
    assert err.value.code == "OUTPUT_EXISTS"
    with BatchLock(config.output_root), pytest.raises(CaptureError) as err:
        capture(config, make_request(config, output_dir=str(config.output_root / "other")))
    assert err.value.code == "BATCH_LOCKED"


def test_a_failed_start_still_leaves_a_manifest(config):
    summary, _, desktop = capture(
        config, make_request(config), fail=CaptureError("TV_ALREADY_RUNNING", "quit it first")
    )
    out = config.output_root / "batch"
    assert (summary["state"], summary["error"]["code"]) == ("stopped", "TV_ALREADY_RUNNING")
    assert read_json(out / "capture-manifest.json")["desktop"]["version"] is None
    assert read_json(out / "job.json")["state"] == "failed"
    assert desktop.stopped == 1


def test_a_desktop_version_change_is_flagged(config):
    for name, manifest in {
        "old": {
            "tool": {"name": "tradingview-capture-mcp"},
            "state": "finished",
            "totals": {"succeeded": 1},
            "finishedAt": {"unix": 5},
            "desktop": {"version": "3.4.0"},
        },
        "stopped": {
            "tool": {"name": "tradingview-capture-mcp"},
            "state": "stopped",
            "totals": {"succeeded": 0},
            "finishedAt": {"unix": 9},
            "desktop": {"version": "1.0.0"},
        },
        "foreign": {"schemaVersion": 1, "records": []},
    }.items():
        (config.output_root / name).mkdir()
        write_json_new(config.output_root / name / "capture-manifest.json", manifest)
    summary, _, _ = capture(config, make_request(config))
    manifest = read_json(config.output_root / "batch" / "capture-manifest.json")
    assert summary["desktopVersionChanged"] is True
    assert manifest["desktop"]["previousVersion"] == "3.4.0"


@pytest.mark.parametrize(
    "changes",
    [
        {"layout": "bad/layout"},
        {"symbols": ()},
        {"symbols": (SYMBOLS[0], SYMBOLS[0])},
        {"symbols": ("btcusdt",)},
        {"symbols": ("A:B!", "A:B&")},
        {"timeframe": "4H"},
        {"ready_timeout_sec": 1.0},
        {"viewport": Viewport(10, 10, 1.0)},
        {"required_studies": ("",)},
    ],
)
def test_invalid_requests_are_rejected(config, changes):
    with pytest.raises(CaptureError) as err:
        validate_request(make_request(config, **changes))
    assert err.value.code == "INVALID_ARGUMENT"


def test_requests_round_trip_through_json(config):
    request = make_request(config)
    assert CaptureRequest.from_dict(json.loads(json.dumps(request.to_dict()))) == request
    with pytest.raises(CaptureError):
        CaptureRequest.from_dict({"layout": "Layout01"})
