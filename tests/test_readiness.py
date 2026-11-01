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


def verdict(current, *, previous="same", before=None, elapsed=0.0, required_studies=()):
    return judge(
        target=TARGET,
        timeframe="1D",
        current=current,
        previous=current if previous == "same" else previous,
        before_switch=before,
        elapsed=elapsed,
        required_studies=required_studies,
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


@pytest.mark.parametrize("study_fields", [{"studies": []}, {"studies": None}, {}])
def test_required_study_cannot_be_ready_when_the_study_list_is_empty(study_fields):
    current = ReadySnapshot.from_page(
        {"symbol": TARGET, "resolution": "1D", "lastBarTime": 2000, **study_fields}
    )
    result = verdict(current, required_studies=("Alpha",))
    assert (result.ready, result.reason) == (False, "missing:Alpha")


def test_every_required_study_must_be_present():
    result = verdict(snap(), required_studies=("Alpha", "Beta"))
    assert (result.ready, result.reason) == (False, "missing:Beta")


def test_required_studies_match_substrings_of_study_names():
    current = snap(studies=(("s1", "Alpha Suite", 2, 2000, "a"), ("s2", "Beta Suite", 2, 2000, "b")))
    result = verdict(current, required_studies=("Alpha", "Beta"))
    assert (result.ready, result.reason) == (True, None)
    assert verdict(current, previous=None, required_studies=("Alpha", "Beta")).reason == "unstable"


def test_wait_until_ready_waits_for_missing_required_studies_to_reappear_and_stabilize():
    complete = snap(studies=(("s1", "Alpha Suite", 2, 2000, "a"), ("s2", "Beta Suite", 2, 2000, "b")))
    reads = iter([snap(studies=()), snap(studies=()), complete, complete])
    now = [0.0]
    result, snapshot, polls, waited = wait_until_ready(
        lambda: next(reads),
        target=TARGET,
        timeframe="1D",
        before_switch=None,
        required_studies=("Alpha", "Beta"),
        timeout=5,
        sleep=lambda s: now.__setitem__(0, now[0] + s),
        clock=lambda: now[0],
    )
    assert result.ready and snapshot == complete and polls == 4 and waited == 3.0


@pytest.mark.parametrize(
    "current, required_studies, reason",
    [(snap(studies=()), ("Alpha",), "missing:Alpha"), (snap(), ("Alpha", "Beta"), "missing:Beta")],
)
def test_missing_required_studies_time_out_with_the_missing_name(current, required_studies, reason):
    now = [0.0]
    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            lambda: current,
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            required_studies=required_studies,
            timeout=3,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail == {"reason": reason, "polls": 4, "symbol": TARGET}
    assert now[0] == 3.0


def test_stable_chart_without_studies_is_ready_when_no_studies_are_required():
    current = snap(studies=())
    assert verdict(current).ready
    now = [0.0]
    result, snapshot, polls, waited = wait_until_ready(
        lambda: current,
        target=TARGET,
        timeframe="1D",
        before_switch=None,
        timeout=3,
        sleep=lambda s: now.__setitem__(0, now[0] + s),
        clock=lambda: now[0],
    )
    assert result.ready and snapshot == current and polls == 2 and waited == 1.0


@pytest.mark.parametrize("timeout, expected_sleeps", [(0.2, [0.2]), (1.2, [1.0, 0.2])])
def test_wait_until_ready_never_sleeps_beyond_the_deadline(timeout, expected_sleeps):
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            lambda: snap(studies=()),
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            required_studies=("Alpha",),
            timeout=timeout,
            sleep=sleep,
            clock=lambda: now[0],
        )
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail["reason"] == "missing:Alpha"
    assert err.value.detail["polls"] == len(expected_sleeps) + 1
    assert sleeps == pytest.approx(expected_sleeps)
    assert now[0] == pytest.approx(timeout)


@pytest.mark.parametrize("late_studies, reason", [(snap().studies, "deadline"), ((), "missing:Alpha")])
def test_wait_until_ready_rejects_reads_that_finish_after_the_deadline(late_studies, reason):
    now = [0.0]
    reads = [0]

    def read():
        reads[0] += 1
        if reads[0] == 2:
            now[0] += 0.3
            return ReadySnapshot(TARGET, "1D", 2000, late_studies)
        return snap()

    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            read,
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            required_studies=("Alpha",),
            timeout=1.2,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail == {"reason": reason, "polls": 2, "symbol": TARGET}
    assert now[0] == 1.3


def test_wait_until_ready_accepts_a_ready_read_exactly_at_the_deadline():
    now = [0.0]
    result, _, polls, waited = wait_until_ready(
        snap,
        target=TARGET,
        timeframe="1D",
        before_switch=None,
        required_studies=("Alpha",),
        timeout=1,
        sleep=lambda s: now.__setitem__(0, now[0] + s),
        clock=lambda: now[0],
    )
    assert result.ready and polls == 2 and waited == 1.0


def test_zero_timeout_allows_one_immediate_read_without_sleeping():
    now = [0.0]
    sleeps = []
    with pytest.raises(CaptureError) as err:
        wait_until_ready(
            snap,
            target=TARGET,
            timeframe="1D",
            before_switch=None,
            required_studies=("Alpha",),
            timeout=0,
            sleep=sleeps.append,
            clock=lambda: now[0],
        )
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail == {"reason": "unstable", "polls": 1, "symbol": TARGET}
    assert sleeps == []
