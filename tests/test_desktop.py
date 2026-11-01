import json
import socket
import stat
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from tradingview_capture_mcp import desktop
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.errors import CaptureError

FAKE_APP = """import json, os, sys
# Like an Electron app, the fake starts as plain Node, without a window or port, when this is set.
if os.environ.get("ELECTRON_RUN_AS_NODE"):
    sys.exit(0)
from http.server import BaseHTTPRequestHandler
from loopback_http import LoopbackHTTPServer
port = int([a for a in sys.argv[1:] if a.startswith("--remote-debugging-port=")][0].split("=", 1)[1])
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        info = {"Browser": "Chrome/146.0.7680.216",
                "User-Agent": "Mozilla/5.0 Electron/41.7.1 TVDesktop/9.9.9"}
        body = json.dumps(info if self.path == "/json/version" else []).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
LoopbackHTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def fake_app(tmp_path, monkeypatch):
    app = tmp_path / "TradingView.app"
    binary = app / "Contents" / "MacOS" / "TradingView"
    binary.parent.mkdir(parents=True)
    # The fake imports tests/loopback_http.py, so put this folder on its path.
    prelude = f"#!{sys.executable}\nimport sys; sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
    binary.write_text(prelude + FAKE_APP, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [])
    return Config(app_path=app, debug_port=free_port(), output_root=tmp_path)


def test_launch_reports_the_version_and_stops_its_own_process(fake_app):
    session = desktop.launch(fake_app, startup_timeout=15)
    try:
        assert (session.version, session.browser) == ("9.9.9", "Chrome/146.0.7680.216")
        assert desktop.listening_addresses(fake_app.debug_port) == ["127.0.0.1"]
    finally:
        desktop.stop_process(session.process, timeout=5)
    assert session.process.poll() is not None


def test_launch_drops_what_would_start_the_app_as_plain_node(fake_app, monkeypatch):
    # An MCP host built on Electron or Node can pass these down to the server, and so to TradingView Desktop.
    monkeypatch.setenv("ELECTRON_RUN_AS_NODE", "1")
    monkeypatch.setenv("NODE_OPTIONS", "--require /nonexistent.js")
    session = desktop.launch(fake_app, startup_timeout=10)
    try:
        assert session.version == "9.9.9"
    finally:
        desktop.stop_process(session.process)


def test_the_app_environment_keeps_everything_else():
    environ = {
        "HOME": "/h",
        "LANG": "C",
        "ELECTRON_RUN_AS_NODE": "1",
        "DYLD_INSERT_LIBRARIES": "x",
        "NODE_PATH": "y",
    }
    assert desktop.app_environment(environ) == {"HOME": "/h", "LANG": "C"}


def test_refuses_when_tradingview_already_runs(fake_app, monkeypatch):
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [4242])
    with pytest.raises(CaptureError) as err:
        desktop.launch(fake_app)
    assert err.value.code == "TV_ALREADY_RUNNING"
    assert err.value.detail == {"pids": [4242]}
    # The message is what an agent sees; it must say why and what the user has to do.
    for hint in ("debugging port", "full screen", "Cmd+Q", "never kill", "capture_retry"):
        assert hint in err.value.message


def test_refuses_when_the_port_is_taken(fake_app):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", fake_app.debug_port))
        busy.listen()
        with pytest.raises(CaptureError) as err:
            desktop.launch(fake_app)
    assert err.value.code == "PORT_IN_USE"


def test_refuses_a_port_open_beyond_loopback_and_stops_the_app(fake_app, monkeypatch):
    calls = []

    def addresses(port):
        calls.append(port)
        return [] if len(calls) == 1 else ["*"]

    started = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    monkeypatch.setattr(desktop, "listening_addresses", addresses)
    monkeypatch.setattr(desktop.subprocess, "Popen", popen)
    with pytest.raises(CaptureError) as err:
        desktop.launch(fake_app, startup_timeout=15)
    assert err.value.code == "CDP_NOT_LOCAL"
    assert started[0].poll() is not None


def test_missing_app(tmp_path):
    with pytest.raises(CaptureError) as err:
        desktop.launch(Config(app_path=tmp_path / "Nope.app", debug_port=free_port(), output_root=tmp_path))
    assert err.value.code == "TV_NOT_INSTALLED"


def test_parse_version():
    assert desktop.parse_version({"User-Agent": "Mozilla/5.0 TVDesktop/3.4.1"}) == "3.4.1"
    assert desktop.parse_version({}) == "unknown"


def test_listening_addresses_parses_lsof(monkeypatch):
    output = "p100\nf20\nn127.0.0.1:9333\np100\nf21\nn[::1]:9333\n"
    monkeypatch.setattr(
        desktop.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=output, stderr="")
    )
    assert desktop.listening_addresses(9333) == ["127.0.0.1", "[::1]"]


def test_wait_for_chart_page_retries_until_the_tab_appears(monkeypatch):
    answers = [
        [],
        [
            {
                "type": "page",
                "url": "https://www.tradingview.com/chart/AbCd1234/",
                "webSocketDebuggerUrl": "ws://x",
            }
        ],
    ]
    monkeypatch.setattr(desktop.cdp, "http_json", lambda port, path, timeout=3.0: answers.pop(0))
    monkeypatch.setattr(desktop.time, "sleep", lambda seconds: None)
    assert desktop.wait_for_chart_page(9333, "AbCd1234", timeout=5)["webSocketDebuggerUrl"] == "ws://x"


def test_a_layout_no_tab_shows_says_what_the_tabs_were_and_what_to_do(monkeypatch):
    # TradingView loads the layout from its servers: with the network down at startup, no tab ever shows it.
    tabs = [
        {"type": "page", "url": "https://www.tradingview.com/chart/Other999/"},
        {"type": "page", "url": "file:///app/window/index.html"},
        {"type": "worker", "url": "https://www.tradingview.com/chart/AbCd1234/"},
    ]
    monkeypatch.setattr(desktop.cdp, "http_json", lambda port, path, timeout=3.0: tabs)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=0)
    assert err.value.code == "LAYOUT_NOT_FOUND"
    assert err.value.detail == {
        "layout": "AbCd1234",
        "waitedSec": 0,
        "targetList": True,
        "pages": 2,
        "chartPages": 1,
        "targetObservation": {
            "polls": 1,
            "targetListReads": 1,
            "targetListErrors": {},
            "pageCounts": [2],
            "chartPageCounts": [1],
            "countsTruncated": False,
        },
    }
    for hint in ("network", "layout ID", "capture_retry"):
        assert hint in err.value.message


def test_a_target_list_that_never_loads_is_reported_as_such(monkeypatch):
    def refuse(port, path, timeout=3.0):
        raise OSError("connection refused")

    monkeypatch.setattr(desktop.cdp, "http_json", refuse)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=0)
    assert (err.value.code, err.value.detail["targetList"]) == ("LAYOUT_NOT_FOUND", False)
    assert "target list" in err.value.message


@pytest.fixture
def chart_page_clock(monkeypatch):
    class Clock:
        value = 0.0

        def now(self):
            return self.value

        def sleep(self, seconds):
            self.value += seconds

    clock = Clock()
    monkeypatch.setattr(desktop.time, "monotonic", clock.now)
    monkeypatch.setattr(desktop.time, "sleep", clock.sleep)
    return clock


def test_stalled_other_layout_records_counts_without_navigation_or_private_data(
    monkeypatch, chart_page_clock
):
    targets = [
        {
            "type": "page",
            "id": "target-id-marker",
            "url": "https://www.tradingview.com/chart/Other999/?token=secret-marker",
            "webSocketDebuggerUrl": "ws://secret-marker",
        },
        {"type": "page", "url": "file:///app/window/index.html"},
        {"type": "worker", "url": "https://www.tradingview.com/chart/AbCd1234/"},
    ]
    monkeypatch.setattr(desktop.cdp, "http_json", lambda port, path, timeout=3.0: targets)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=3)
    assert chart_page_clock.value == 3
    assert err.value.code == "LAYOUT_NOT_FOUND"
    observation = err.value.detail["targetObservation"]
    assert observation == {
        "polls": 4,
        "targetListReads": 4,
        "targetListErrors": {},
        "pageCounts": [2],
        "chartPageCounts": [1],
        "countsTruncated": False,
    }
    encoded = json.dumps(observation)
    for private in ("AbCd1234", "Other999", "secret-marker", "target-id-marker", "https:", "ws:"):
        assert private not in encoded


def test_target_list_failures_are_classified_without_raw_error_text(monkeypatch, chart_page_clock):
    secret = "https://private.invalid/chart/Other999/?token=secret-marker"
    http_error = urllib.error.HTTPError(secret, 503, secret, {}, None)
    http_error.close()
    answers = iter(
        [
            http_error,
            urllib.error.URLError(TimeoutError(secret)),
            json.JSONDecodeError(secret, secret, 0),
            OSError(secret),
            [],
            [{"type": "page", "url": "https://www.tradingview.com/chart/Other999/"}],
        ]
    )

    def read(port, path, timeout=3.0):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(desktop.cdp, "http_json", read)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=5)
    assert chart_page_clock.value == 5
    assert err.value.detail["targetList"] is True
    observation = err.value.detail["targetObservation"]
    assert observation == {
        "polls": 6,
        "targetListReads": 2,
        "targetListErrors": {"http": 1, "timeout": 1, "invalidResponse": 1, "transport": 1},
        "pageCounts": [0, 1],
        "chartPageCounts": [0, 1],
        "countsTruncated": False,
    }
    assert secret not in json.dumps(observation)
    assert "secret-marker" not in json.dumps(observation)


def test_target_observation_bounds_distinct_counts(monkeypatch, chart_page_clock):
    counts = iter(range(11))

    def read(port, path, timeout=3.0):
        return [
            {"type": "page", "url": "https://www.tradingview.com/chart/Other999/"}
            for _ in range(next(counts))
        ]

    monkeypatch.setattr(desktop.cdp, "http_json", read)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=10)
    observation = err.value.detail["targetObservation"]
    assert observation["polls"] == observation["targetListReads"] == 11
    assert observation["pageCounts"] == observation["chartPageCounts"] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert observation["countsTruncated"] is True


def test_target_appearing_after_list_failure_still_succeeds(monkeypatch, chart_page_clock):
    target = {
        "type": "page",
        "url": "https://www.tradingview.com/chart/AbCd1234/",
        "webSocketDebuggerUrl": "ws://synthetic-target",
    }
    answers = iter([TimeoutError("not retained"), [], [target]])

    def read(port, path, timeout=3.0):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(desktop.cdp, "http_json", read)
    assert desktop.wait_for_chart_page(9333, "AbCd1234", timeout=3) is target
    assert chart_page_clock.value == 2


def test_ambiguous_layout_is_still_rejected_without_waiting(monkeypatch, chart_page_clock):
    targets = [{"type": "page", "url": "https://www.tradingview.com/chart/AbCd1234/"}] * 2
    monkeypatch.setattr(desktop.cdp, "http_json", lambda port, path, timeout=3.0: targets)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=3)
    assert err.value.code == "LAYOUT_NOT_UNIQUE"
    assert chart_page_clock.value == 0
