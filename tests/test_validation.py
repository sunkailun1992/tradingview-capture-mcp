import pytest

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.validation import (
    SYMBOL_RE,
    TIMEFRAME_RE,
    check_layout,
    history_from_time,
    same_symbol,
)


@pytest.mark.parametrize("code", ["BINANCE:BTCUSDT.P", "NYMEX:CL1!", "SSE_DLY:000001", "OANDA:XAUUSD"])
def test_accepts_tradingview_codes(code):
    assert SYMBOL_RE.fullmatch(code)


@pytest.mark.parametrize("code", ["BTCUSDT", "binance:BTCUSDT", "BINANCE:", "BINANCE:BTC USDT", "A:B;rm"])
def test_rejects_other_symbol_strings(code):
    assert not SYMBOL_RE.fullmatch(code)


@pytest.mark.parametrize("value", ["1D", "D", "240", "1W", "1M", "15S"])
def test_accepts_resolutions(value):
    assert TIMEFRAME_RE.fullmatch(value)


@pytest.mark.parametrize("value", ["4H", "0", "1d", "", "10000"])
def test_rejects_other_resolutions(value):
    assert not TIMEFRAME_RE.fullmatch(value)


def test_check_layout():
    assert check_layout("Abc12345") == "Abc12345"
    with pytest.raises(CaptureError) as err:
        check_layout("../x")
    assert err.value.code == "INVALID_ARGUMENT"


@pytest.mark.parametrize(
    "actual, requested, expected",
    [
        ("BINANCE:BTCUSDT.P", "BINANCE:BTCUSDT.P", True),
        ("NYMEX_DL:CL1!", "NYMEX:CL1!", True),
        ("SSE_DLY:000001", "SSE:000001", True),
        ("BINANCE:ETHUSDT.P", "BINANCE:BTCUSDT.P", False),
        ("NYMEX_XX:CL1!", "NYMEX:CL1!", False),
        ("", "BINANCE:BTCUSDT.P", False),
    ],
)
def test_same_symbol_accepts_delayed_feeds(actual, requested, expected):
    assert same_symbol(actual, requested) is expected


@pytest.mark.parametrize(
    "value, expected",
    [("2019-01-02", 1546387200), ("1970-01-01", 0), ("1800-01-01", -5364662400), ("2024-02-29", 1709164800)],
)
def test_history_from_is_midnight_utc_of_the_date(value, expected):
    assert history_from_time(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "2019-1-2",
        "2019/01/02",
        "20190102",
        "2019-13-01",
        "2019-02-30",
        "1799-12-31",
        "",
        " 2019-01-02",
        "2019-01-02T00:00",
        20190102,
    ],
)
def test_rejects_other_history_dates(value):
    with pytest.raises(CaptureError) as err:
        history_from_time(value)
    assert err.value.code == "INVALID_ARGUMENT"
