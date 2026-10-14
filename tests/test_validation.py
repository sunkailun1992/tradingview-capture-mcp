import pytest

from tradingview_capture_mcp.errors import CaptureError
from tradingview_capture_mcp.validation import SYMBOL_RE, TIMEFRAME_RE, check_layout, same_symbol


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
