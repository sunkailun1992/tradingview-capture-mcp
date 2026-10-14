import copy

import pytest
from fakes import OK_DIAGNOSE, FakeChart, FakeClock

from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.diagnostics import problems, run_doctor, wait_for_internals
from tradingview_capture_mcp.errors import CaptureError


def test_a_healthy_report_has_no_problems():
    assert problems(OK_DIAGNOSE) == []


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (
            lambda r: r["checks"].__setitem__(0, {"name": "activeChart", "ok": False, "error": "gone"}),
            "activeChart",
        ),
        (lambda r: r["checks"][0].__setitem__("detail", ["setSymbol"]), "activeChart.methods"),
        (lambda r: r["checks"][1].__setitem__("detail", "undefined"), "takeClientScreenshot.function"),
        (lambda r: r["checks"][3]["detail"].__setitem__("valueAt", "undefined"), "mainSeriesBars.methods"),
        (lambda r: r["checks"][6]["detail"][0].__setitem__("collections", ["dwglabels"]), "studies.shape"),
        (lambda r: r["checks"].pop(), "shapes"),
    ],
)
def test_each_missing_piece_is_named(mutate, expected):
    report = copy.deepcopy(OK_DIAGNOSE)
    mutate(report)
    assert expected in problems(report)


def test_doctor_checks_the_layout_before_starting_anything(tmp_path):
    config = Config(app_path=tmp_path / "TradingView.app", debug_port=9333, output_root=tmp_path)
    with pytest.raises(CaptureError) as err:
        run_doctor(config, "../bad")
    assert err.value.code == "INVALID_ARGUMENT"


def test_wait_for_internals_polls_until_the_page_is_built():
    loading = copy.deepcopy(OK_DIAGNOSE)
    loading["checks"][2] = {"name": "chartWidget", "ok": False, "error": "not built yet"}
    clock = FakeClock()
    found, report = wait_for_internals(
        FakeChart(diagnose_sequence=[loading, loading]), timeout=30, sleep=clock.sleep, clock=clock
    )
    assert (found, report) == ([], OK_DIAGNOSE)
    assert clock.now == 2


def test_wait_for_internals_gives_up_with_the_last_problems():
    broken = copy.deepcopy(OK_DIAGNOSE)
    broken["checks"][2] = {"name": "chartWidget", "ok": False, "error": "gone"}
    clock = FakeClock()
    found, _ = wait_for_internals(FakeChart(diagnose=broken), timeout=5, sleep=clock.sleep, clock=clock)
    assert found == ["chartWidget"]
    assert clock.now >= 5
