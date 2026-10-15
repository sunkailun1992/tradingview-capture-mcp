import pytest
from fakes import FakeClock

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.history import MAX_REQUEST, HistoryState, load_history, request_size

SYMBOL = "KRX:AAAAAA"
HOUR = 3600
TARGET = 1_000_000


def state(**fields):
    raw = {
        "symbol": SYMBOL,
        "resolution": "60",
        "bars": 301,
        "firstBarTime": TARGET + 300 * HOUR,
        "lastBarTime": TARGET + 600 * HOUR,
        "loading": False,
        "canRequest": True,
        "endOfData": None,
        "requested": 0,
    }
    raw.update(fields)
    return HistoryState.from_page(raw)


class FakeSeries:
    """The history script's answers: a request is answered `delay` reads later, nothing older than `floor`."""

    def __init__(
        self,
        *,
        bars=301,
        first=TARGET + 300 * HOUR,
        floor=None,
        delay=1,
        answers=True,
        symbol=SYMBOL,
        live=False,
        refuse=False,
        empty=False,
    ):
        self.bars, self.first, self.last = bars, first, first + (bars - 1) * HOUR
        self.floor, self.delay, self.answers, self.symbol = floor, delay, answers, symbol
        self.live = live  # an open market: every read sees one more bar at the end
        self.refuse = refuse  # the series turns every request down without sending it
        self.empty = empty  # every answer comes back without bars and without an end flag
        self.end = None
        self.pending = None  # [count, reads left]
        self.requests = []

    def __call__(self, request):
        if self.live:
            self.bars, self.last = self.bars + 1, self.last + HOUR
        if self.pending is not None:
            self.pending[1] -= 1
            if self.pending[1] <= 0 and self.answers:
                count = 0 if self.empty else self.pending[0]
                oldest = self.first - count * HOUR
                if self.floor is not None and oldest <= self.floor:
                    count, oldest, self.end = (self.first - self.floor) // HOUR, self.floor, "limit"
                self.bars, self.first, self.pending = self.bars + count, oldest, None
        loading = self.pending is not None
        raw = {
            "symbol": self.symbol,
            "resolution": "60",
            "bars": self.bars,
            "firstBarTime": self.first,
            "lastBarTime": self.last,
            "loading": loading,
            "canRequest": not loading,
            "endOfData": self.end,
            "requested": 0,
        }
        if request and not loading and self.end is None and not self.refuse:
            self.requests.append(request)
            self.pending = [request, self.delay]
            raw["requested"] = request
        return raw


def load(series, *, target=TARGET, timeout=60.0):
    clock = FakeClock()
    result = load_history(
        lambda request: HistoryState.from_page(series(request)),
        symbol=SYMBOL,
        target=target,
        timeout=timeout,
        sleep=clock.sleep,
        clock=clock,
    )
    return result, clock


def test_request_size_covers_the_gap_at_the_loaded_spacing_with_a_margin():
    # 301 hourly bars span 300 hours; the target lies 300 hours before the first bar.
    assert request_size(state(), TARGET) == 330


def test_request_size_is_capped_and_never_zero_while_the_target_is_ahead():
    far = TARGET + 10**6 * HOUR
    assert request_size(state(firstBarTime=far, lastBarTime=far + 300 * HOUR), TARGET) == MAX_REQUEST
    assert request_size(state(firstBarTime=TARGET + 1), TARGET) == 1


def test_request_size_without_a_spacing_asks_for_the_most():
    assert request_size(state(bars=1, lastBarTime=TARGET + 300 * HOUR), TARGET) == MAX_REQUEST
    assert request_size(state(bars=0, firstBarTime=None, lastBarTime=None), TARGET) == MAX_REQUEST


def test_nothing_is_asked_once_the_first_bar_is_at_the_target():
    assert request_size(state(firstBarTime=TARGET), TARGET) == 0
    assert state(firstBarTime=TARGET).reached(TARGET)
    assert not state(firstBarTime=TARGET + 1).reached(TARGET)


def test_loads_until_the_first_bar_is_at_or_before_the_target():
    series = FakeSeries(first=TARGET + 9000 * HOUR, bars=301)
    result, clock = load(series)
    assert result.after.reached(TARGET)
    assert result.after.end_of_data is None
    assert series.requests[0] == MAX_REQUEST  # a long way off: the most at once
    assert result.requests == len(series.requests) == 2
    assert (result.before.bars, result.after.bars) == (301, 301 + sum(series.requests))
    assert result.waited == clock.now


def test_stops_where_tradingview_has_no_older_bars():
    series = FakeSeries(floor=TARGET + 100 * HOUR)
    result, _ = load(series)
    assert not result.after.reached(TARGET)
    assert (result.after.end_of_data, result.after.first_bar_time) == ("limit", TARGET + 100 * HOUR)
    assert result.requests == 1


def test_a_chart_that_already_reaches_the_target_is_not_asked_for_more():
    series = FakeSeries(first=TARGET - HOUR)
    result, clock = load(series)
    assert series.requests == []
    assert result.requests == 0
    assert clock.now == 1.0  # two equal reads


def test_an_end_flag_from_the_first_load_needs_no_request():
    series = FakeSeries()
    series.end = "limit"  # a young symbol: TradingView sent everything it has with the chart's first load
    result, _ = load(series)
    assert (series.requests, result.after.end_of_data) == ([], "limit")


def test_a_request_that_is_never_answered_times_out():
    series = FakeSeries(answers=False)
    with pytest.raises(CaptureError) as err:
        load(series, timeout=10)
    assert err.value.code == "NOT_READY_TIMEOUT"
    assert err.value.detail["reason"] == "history"
    assert err.value.detail["requests"] == 1


def test_the_chart_leaving_the_symbol_stops_the_load():
    series = FakeSeries(symbol="KRX:BBBBBB")
    with pytest.raises(CaptureError) as err:
        load(series)
    assert err.value.code == "SYMBOL_NOT_FOUND"


def test_a_delayed_feed_name_is_the_same_symbol():
    series = FakeSeries(first=TARGET, symbol="KRX_DLY:AAAAAA")
    result, _ = load(series)
    assert result.after.reached(TARGET)


def test_new_bars_at_the_end_do_not_hold_the_load_back():
    series = FakeSeries(first=TARGET + 50 * HOUR, live=True)
    result, clock = load(series)
    assert result.after.reached(TARGET)
    assert clock.now == 2.0  # one request, then two reads with the same first bar


def test_a_span_shorter_than_a_second_asks_for_the_most():
    tight = state(bars=2, firstBarTime=TARGET + 10, lastBarTime=TARGET + 10.5)
    assert request_size(tight, TARGET) == MAX_REQUEST


def test_refused_requests_end_in_a_timeout():
    series = FakeSeries(refuse=True)
    with pytest.raises(CaptureError) as err:
        load(series, timeout=5)
    assert (err.value.code, err.value.detail["reason"], err.value.detail["requests"]) == (
        "NOT_READY_TIMEOUT",
        "history",
        0,
    )


def test_answers_without_bars_are_asked_again_until_the_timeout():
    series = FakeSeries(empty=True)
    with pytest.raises(CaptureError) as err:
        load(series, timeout=5)
    assert (err.value.code, err.value.detail["reason"]) == ("NOT_READY_TIMEOUT", "history")
    assert err.value.detail["firstBarTime"] == TARGET + 300 * HOUR
    assert err.value.detail["requests"] == len(series.requests) > 1
