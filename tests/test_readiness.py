import pytest

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.readiness import ReadySnapshot, judge, normalize_resolution, wait_until_ready

TARGET = "BINANCE:AAAUSDT.P"


def snap(symbol=TARGET, resolution="1D", last=2000, studies=(("s1", "Alpha", 2, 2000, "new"),)):
    return ReadySnapshot.from_page(
        {
            "symbol": symbol,
            "resolution": resolution,
            "lastBarTime": last,
            "studies": [
                {"id": i, "name": n, "status": st, "lastTime": lt, "digest": d} for i, n, st, lt, d in studies
            ],
        }
    )


def verdict(current, *, previous="same", before=None, elapsed=0.0):
    return judge(
        target=TARGET,
        timeframe="1D",
        current=current,
        previous=current if previous == "same" else previous,
        before_switch=before,
        elapsed=elapsed,
    )


def test_ready_when_everything_lines_up():
    assert verdict(snap()).ready


@pytest.mark.parametrize(
    "current, reason",
    [
        (snap(symbol="BINANCE:OLDUSDT.P"), "symbol"),
        (snap(resolution="240"), "resolution"),
        (snap(last=None), "bars"),
        (snap(studies=(("s1", "Alpha", 1, 2000, "new"),)), "status:Alpha"),
        (snap(studies=(("s1", "Alpha", 2, 1000, "new"),)), "lastTime:Alpha"),
    ],
)
def test_each_unmet_condition_is_named(current, reason):
    result = verdict(current)
    assert (result.ready, result.reason) == (False, reason)


def test_daily_resolutions_compare_equal():
    assert normalize_resolution("D") == normalize_resolution("1D") == "1D"
    assert verdict(snap(resolution="D")).ready


def test_two_structurally_equal_reads_are_required():
    assert verdict(snap(), previous=None).reason == "unstable"
    assert verdict(snap(), previous=snap(studies=(("s1", "Alpha", 2, 1000, "new"),))).reason == "unstable"
    assert verdict(snap(), previous=snap(last=1000)).reason == "unstable"


def test_a_ticking_market_still_counts_as_stable():
    ticking = snap(studies=(("s1", "Alpha", 2, 2000, "price moved"),))
    assert verdict(snap(), previous=ticking).ready


def test_the_timeout_reports_the_last_symbol_seen():
    now = [0.0]
    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            lambda: snap(symbol="SSE_DLY:000001"),
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            timeout=3,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )
    assert err.value.detail["symbol"] == "SSE_DLY:000001"


def test_stale_tables_wait_for_the_grace_period():
    before = snap(symbol="BINANCE:OLDUSDT.P", studies=(("s1", "Alpha", 2, 2000, "new"),))
    early = verdict(snap(), before=before, elapsed=3.0)
    assert (early.ready, early.reason, early.unchanged) == (False, "unchanged:Alpha", ("Alpha",))
    late = verdict(snap(), before=before, elapsed=10.0)
    assert (late.ready, late.unchanged) == (True, ("Alpha",))


def test_unchanged_data_is_fine_when_the_symbol_did_not_change():
    assert verdict(snap(), before=snap(), elapsed=0.0).ready


def test_unchanged_data_is_fine_when_the_chart_already_showed_the_delayed_feed():
    # The restored layout can show the target under its delayed-feed name; that is the same symbol.
    result = verdict(snap(), before=snap(symbol="BINANCE_DLY:AAAUSDT.P"), elapsed=0.0)
    assert (result.ready, result.unchanged) == (True, ())


def test_wait_until_ready_polls_until_stable():
    reads = iter([snap(studies=(("s1", "Alpha", 1, 2000, "new"),)), snap(), snap()])
    now = [0.0]
    result, snapshot, polls, waited = wait_until_ready(
        lambda: next(reads),
        target=TARGET,
        timeframe="1D",
        before_switch=None,
        timeout=30,
        sleep=lambda s: now.__setitem__(0, now[0] + s),
        clock=lambda: now[0],
    )
    assert result.ready and snapshot == snap() and polls == 3 and waited == 2.0


def test_wait_until_ready_times_out_with_the_reason():
    now = [0.0]
    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            lambda: snap(symbol="BINANCE:OLDUSDT.P"),
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            timeout=5,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail["reason"] == "symbol"


def test_studies_still_moving_at_the_read_are_named():
    ticking = snap(studies=(("s1", "Alpha", 2, 2000, "price moved"),))
    result = verdict(snap(), previous=ticking)
    assert result.ready
    assert result.moving == ("Alpha",)
    assert verdict(snap()).moving == ()
