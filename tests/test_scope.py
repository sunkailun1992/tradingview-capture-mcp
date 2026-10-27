"""The hard rules in AGENTS.md, checked on the source so a change that breaks one fails before review."""

import re
from importlib import resources
from pathlib import Path

import pytest

from tradingview_capture_mcp import page

SOURCE = Path(__file__).resolve().parents[1] / "src" / "tradingview_capture_mcp"
# The only scripts that may change the chart: symbol and resolution, and loading older bars.
CHANGES_ALLOWED = {"switch": ("setSymbol", "setResolution"), "history": ("requestMoreData",)}
CHART_CHANGES = tuple(name for names in CHANGES_ALLOWED.values() for name in names)
# Chart API calls that would change what the user sees or keeps: studies, drawings, view, panes, properties.
FORBIDDEN_CALLS = (
    "createStudy",
    "createShape",
    "createMultipointShape",
    "removeEntity",
    "removeAllShapes",
    "removeAllStudies",
    "setVisibleRange",
    "setChartType",
    "setTimezone",
    "setAllPanesHeight",
    "setMaximized",
    "setHeight",
    "collapse",
    "executeActionById",
    "applyOverrides",
    "setProperties",
    "setInputValues",
    "setVisible",
    "showWidget",
    "scrollToRealtime",
    "zoomToBarsRange",
)
# Page features the export never needs: UI events, network, storage, cookies and code from strings.
FORBIDDEN_PAGE = (
    ".click(",
    "dispatchEvent",
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "sendBeacon",
    "window.open",
    "eval(",
    "new Function",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
)


def _script(name: str) -> str:
    folder = resources.files("tradingview_capture_mcp").joinpath("page")
    return folder.joinpath(f"{name}.js").read_text(encoding="utf-8")


def _code(text: str) -> str:
    """The script without its comments, which may name what it must not do."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def _calls(code: str, names: tuple[str, ...]) -> list[str]:
    """The names the code calls; checking that a method exists (typeof chart.setSymbol) is not a call."""
    return [name for name in names if re.search(rf"\b{re.escape(name)}\s*\(", code)]


@pytest.mark.parametrize("name", [*page.SCRIPTS, "common"])
def test_page_scripts_change_nothing_but_symbol_resolution_and_history(name):
    code = _code(_script(name))
    allowed = CHANGES_ALLOWED.get(name, ())
    called = _calls(code, (*CHART_CHANGES, *FORBIDDEN_CALLS))
    assert [call for call in called if call not in allowed] == []
    assert [token for token in FORBIDDEN_PAGE if token in code] == []


def test_the_scope_check_sees_a_forbidden_call():
    assert _calls(_code("chart.showWidget('backtesting');"), FORBIDDEN_CALLS) == ["showWidget"]
    assert _calls(_code("pane.collapse();"), FORBIDDEN_CALLS) == ["collapse"]
    assert _calls(_code("typeof chart.setSymbol === 'function'"), CHART_CHANGES) == []
    assert _calls(_code("// never createStudy() here"), FORBIDDEN_CALLS) == []


def test_no_process_is_stopped_by_name():
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(pkill|killall)\b", text), path


def test_the_devtools_client_only_evaluates_the_fixed_page_scripts():
    methods = set()
    for path in SOURCE.rglob("*.py"):
        methods |= set(re.findall(r"\.call\(\s*\"([^\"]+)\"", path.read_text(encoding="utf-8")))
    assert methods == {"Runtime.evaluate"}
