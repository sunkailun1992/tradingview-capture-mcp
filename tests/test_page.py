import json

import pytest

from tradingview_capture_mcp import page


def test_build_wraps_common_and_script_with_json_args():
    code = page.build("switch", {"symbol": 'BINANCE:"X"', "timeframe": "1D"})
    assert code.startswith("(async () => {\nconst ARGS = ")
    assert code.endswith("\n})()")
    args_line = code.splitlines()[1]
    assert json.loads(args_line[len("const ARGS = ") : -1]) == {"symbol": 'BINANCE:"X"', "timeframe": "1D"}
    assert "function orderedStudies" in code


@pytest.mark.parametrize("name", ["alive", "diagnose"])
def test_standalone_scripts_leave_out_common(name):
    assert "function orderedStudies" not in page.build(name)


def test_every_script_is_packaged():
    assert all(page.build(name) for name in page.SCRIPTS)


def test_unknown_scripts_are_rejected():
    with pytest.raises(ValueError):
        page.build("eval")
