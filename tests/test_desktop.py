import json
import os
import signal
import socket
import stat
import subprocess
import sys
import time
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
from pathlib import Path
from loopback_http import LoopbackHTTPServer
# What it was started with, for the tests to read.
Path(sys.argv[0]).with_name(f"argv-{os.getpid()}.json").write_text(json.dumps(sys.argv[1:]))
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
# Stands in for /usr/bin/open: records its arguments and, like LaunchServices, starts the app with the ones
# after --args in a session of its own, then returns at once; without --args it only "activates" the app.
FAKE_OPEN = """import json, subprocess, sys
from pathlib import Path
here = Path(__file__).parent
args = sys.argv[1:]
with (here / "open-calls.jsonl").open("a") as calls:
    calls.write(json.dumps(args) + "\\n")
if "--args" in args:
    app = Path(args[args.index("-a") + 1])
    child = subprocess.Popen(
        [str(app / "Contents" / "MacOS" / "TradingView"), *args[args.index("--args") + 1:]],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    with (here / "launched.txt").open("a") as launched:
        launched.write(f"{child.pid}\\n")
"""
SWITCHES = [
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_until(condition, seconds=15.0):
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def executable(path, body):
    # The fakes import tests/loopback_http.py, so put this folder on their path.
    prelude = f"#!{sys.executable}\nimport sys; sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prelude + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class World:
    """A fake TradingView Desktop, a fake /usr/bin/open and the TradingView processes that are running."""

    def __init__(self, tmp_path):
        self.root = tmp_path
        self.app = tmp_path / "TradingView.app"
        self.port = free_port()
        self.user_copies = []  # processes a test starts itself, as the user would
        executable(self.app / "Contents" / "MacOS" / "TradingView", FAKE_APP)
        executable(tmp_path / "open", FAKE_OPEN)

    def config(self, **changes):
        return Config(app_path=self.app, debug_port=self.port, output_root=self.root, **changes)

    def launched(self):
        """Processes the fake open started."""
        path = self.root / "launched.txt"
        return [int(line) for line in path.read_text().split()] if path.exists() else []

    def pids(self):
        """What pgrep -x TradingView would list: every fake TradingView still running."""
        return [p.pid for p in self.user_copies if p.poll() is None] + [
            p for p in self.launched() if alive(p)
        ]

    def open_calls(self):
        path = self.root / "open-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def argv(self, pid):
        path = self.app / "Contents" / "MacOS" / f"argv-{pid}.json"
        assert wait_until(path.exists)
        return json.loads(path.read_text())

    def start_user_copy(self):
        """TradingView Desktop opened with the debugging port, as tradingview-capture open would."""
        binary = self.app / "Contents" / "MacOS" / "TradingView"
        process = subprocess.Popen(
            [str(binary), f"--remote-debugging-port={self.port}"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.user_copies.append(process)
        assert wait_until(lambda: desktop.listening_addresses(self.port) == ["127.0.0.1"])
        return process

    def cleanup(self):
        for process in self.user_copies:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        for pid in self.launched():
            if alive(pid):
                os.kill(pid, signal.SIGTERM)
                if not wait_until(lambda pid=pid: not alive(pid), 10):
                    os.kill(pid, signal.SIGKILL)


@pytest.fixture
def world(tmp_path, monkeypatch):
    world = World(tmp_path)
    monkeypatch.setattr(desktop, "OPEN", str(tmp_path / "open"))
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": world.pids())
    try:
        yield world
    finally:
        world.cleanup()


def test_an_open_tradingview_with_the_port_is_used_as_it_is_and_left_running(world):
    user = world.start_user_copy()
    session = desktop.connect_or_launch(world.config(), startup_timeout=15)
    assert (session.pid, session.launched, session.process) == (user.pid, False, None)
    assert (session.version, session.browser) == ("9.9.9", "Chrome/146.0.7680.216")
    desktop.release(session)
    assert user.poll() is None
    assert world.open_calls() == []


@pytest.mark.parametrize("port_held_by_another_program", [False, True])
def test_an_open_tradingview_without_the_port_is_refused_and_left_alone(
    world, monkeypatch, port_held_by_another_program
):
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [4242])
    with socket.socket() as other:
        if port_held_by_another_program:
            other.bind(("127.0.0.1", world.port))
            other.listen()
        with pytest.raises(CaptureError) as err:
            desktop.connect_or_launch(world.config())
    assert err.value.code == "TV_ALREADY_RUNNING"
    assert err.value.detail == {"pids": [4242], "port": world.port}
    # The message is what an agent sees; it must say why and what the user has to do.
    for hint in ("debugging port", "Cmd+Q", "never kill", "tradingview-capture open", "desktop_open"):
        assert hint in err.value.message
    assert "capture_retry" in err.value.message
    assert world.open_calls() == []


def test_an_open_tradingview_whose_port_reaches_beyond_loopback_is_refused_but_not_stopped(
    world, monkeypatch
):
    user = world.start_user_copy()
    monkeypatch.setattr(desktop, "listeners", lambda port: [(user.pid, "*")])
    with pytest.raises(CaptureError) as err:
        desktop.connect_or_launch(world.config())
    assert (err.value.code, err.value.detail) == ("CDP_NOT_LOCAL", {"addresses": ["*"]})
    assert user.poll() is None  # the user's process is never stopped


def test_refuses_a_port_another_program_holds_while_tradingview_is_closed(world):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", world.port))
        busy.listen()
        with pytest.raises(CaptureError) as err:
            desktop.connect_or_launch(world.config())
    assert err.value.code == "PORT_IN_USE"
    assert world.open_calls() == []


def test_a_closed_tradingview_is_started_with_the_port_and_left_running(world):
    session = desktop.connect_or_launch(world.config(), startup_timeout=15)
    assert world.open_calls() == [
        ["-g", "-a", str(world.app), "--args", f"--remote-debugging-port={world.port}", *SWITCHES]
    ]
    assert (session.launched, session.process, session.pid) == (True, None, world.launched()[0])
    assert (session.version, session.browser) == ("9.9.9", "Chrome/146.0.7680.216")
    desktop.release(session)
    assert alive(session.pid)


def test_with_keep_open_off_the_tool_quits_the_tradingview_it_started(world):
    session = desktop.connect_or_launch(world.config(keep_open=False), startup_timeout=15)
    assert world.open_calls() == []
    assert session.launched and session.pid == session.process.pid
    assert world.argv(session.pid) == [f"--remote-debugging-port={world.port}", *SWITCHES]
    desktop.release(session)
    assert session.process.poll() is not None


def test_keep_open_off_never_quits_a_tradingview_that_was_already_open(world):
    user = world.start_user_copy()
    session = desktop.connect_or_launch(world.config(keep_open=False), startup_timeout=15)
    desktop.release(session)
    assert (session.launched, user.poll()) == (False, None)


def test_the_app_starts_without_what_would_make_it_plain_node(world, monkeypatch):
    # An MCP host built on Electron or Node can pass these down to the server, and so to TradingView Desktop.
    monkeypatch.setenv("ELECTRON_RUN_AS_NODE", "1")
    monkeypatch.setenv("NODE_OPTIONS", "--require /nonexistent.js")
    session = desktop.connect_or_launch(world.config(keep_open=False), startup_timeout=10)
    try:
        assert session.version == "9.9.9"
    finally:
        desktop.release(session)


def test_the_app_environment_keeps_everything_else():
    environ = {
        "HOME": "/h",
        "LANG": "C",
        "ELECTRON_RUN_AS_NODE": "1",
        "DYLD_INSERT_LIBRARIES": "x",
        "NODE_PATH": "y",
    }
    assert desktop.app_environment(environ) == {"HOME": "/h", "LANG": "C"}


@pytest.mark.parametrize("keep_open", [True, False])
def test_a_started_tradingview_whose_port_reaches_beyond_loopback_is_stopped(world, monkeypatch, keep_open):
    real_listeners = desktop.listeners

    def beyond_loopback(port):
        found = real_listeners(port)
        return [(pid, "*") for pid, _ in found]

    monkeypatch.setattr(desktop, "listeners", beyond_loopback)
    started = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    monkeypatch.setattr(desktop.subprocess, "Popen", popen)
    with pytest.raises(CaptureError) as err:
        desktop.connect_or_launch(world.config(keep_open=keep_open), startup_timeout=15)
    assert err.value.code == "CDP_NOT_LOCAL"
    if keep_open:
        [pid] = world.launched()
        assert wait_until(lambda: not alive(pid), 25)
    else:
        assert started[0].poll() is not None


def test_a_tradingview_that_never_answers_is_a_startup_timeout(world, monkeypatch, fake_clock):
    monkeypatch.setattr(desktop, "OPEN", "/usr/bin/true")
    with pytest.raises(CaptureError) as err:
        desktop.connect_or_launch(world.config(), startup_timeout=5)
    assert err.value.code == "TV_STARTUP_TIMEOUT"


def test_a_tradingview_macos_cannot_open_fails_at_once(world, monkeypatch, fake_clock):
    monkeypatch.setattr(desktop, "OPEN", "/usr/bin/false")
    with pytest.raises(CaptureError) as err:
        desktop.connect_or_launch(world.config(), startup_timeout=5)
    assert (err.value.code, err.value.detail) == ("TV_STARTUP_TIMEOUT", {"returncode": 1})
    assert fake_clock.value == 0  # it does not wait for a DevTools that cannot come


def test_a_copy_the_user_opened_meanwhile_without_the_port_is_named_as_such(world, monkeypatch, fake_clock):
    # Asked to start it while the user opened one from the Dock, macOS only brings that one to the front.
    monkeypatch.setattr(desktop, "OPEN", "/usr/bin/true")
    reads = []
    monkeypatch.setattr(
        desktop,
        "running_pids",
        lambda process_name="TradingView": reads.append(1) or ([] if len(reads) == 1 else [4242]),
    )
    with pytest.raises(CaptureError) as err:
        desktop.connect_or_launch(world.config(), startup_timeout=5)
    assert (err.value.code, err.value.detail["pids"]) == ("TV_ALREADY_RUNNING", [4242])


def test_missing_app(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [])
    with pytest.raises(CaptureError) as err:
        desktop.connect_or_launch(
            Config(app_path=tmp_path / "Nope.app", debug_port=free_port(), output_root=tmp_path)
        )
    assert err.value.code == "TV_NOT_INSTALLED"


def test_open_for_the_user_starts_tradingview_in_front_and_leaves_it_running(world):
    # The user asked for it, so even keep_open = false leaves it open.
    report = desktop.open_for_user(world.config(keep_open=False), startup_timeout=15)
    [pid] = world.launched()
    assert report == {"state": "started", "port": world.port, "pid": pid, "version": "9.9.9"}
    assert world.open_calls() == [
        ["-a", str(world.app), "--args", f"--remote-debugging-port={world.port}", *SWITCHES]
    ]
    assert alive(pid)


def test_open_for_the_user_brings_a_copy_with_the_port_to_the_front(world):
    user = world.start_user_copy()
    report = desktop.open_for_user(world.config(), startup_timeout=15)
    assert report == {"state": "running", "port": world.port, "pid": user.pid, "version": "9.9.9"}
    assert world.open_calls() == [["-a", str(world.app)]]


def test_open_for_the_user_refuses_a_copy_without_the_port(world, monkeypatch):
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [4242])
    with pytest.raises(CaptureError) as err:
        desktop.open_for_user(world.config())
    assert err.value.code == "TV_ALREADY_RUNNING"
    assert world.open_calls() == []


def test_parse_version():
    assert desktop.parse_version({"User-Agent": "Mozilla/5.0 TVDesktop/3.4.1"}) == "3.4.1"
    assert desktop.parse_version({}) == "unknown"


def test_listeners_parse_lsof(monkeypatch):
    output = "p100\nf20\nn127.0.0.1:9333\nf21\nn[::1]:9333\np200\nf7\nn*:9333\n"
    monkeypatch.setattr(
        desktop.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=output, stderr="")
    )
    assert desktop.listeners(9333) == [(100, "127.0.0.1"), (100, "[::1]"), (200, "*")]
    assert desktop.listening_addresses(9333) == ["127.0.0.1", "[::1]", "*"]


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
    for hint in ("network", "layout ID", "already open", "capture_retry"):
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
def fake_clock(monkeypatch):
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


def test_stalled_other_layout_records_counts_without_navigation_or_private_data(monkeypatch, fake_clock):
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
    assert fake_clock.value == 3
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


def test_target_list_failures_are_classified_without_raw_error_text(monkeypatch, fake_clock):
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
    assert fake_clock.value == 5
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


def test_target_observation_bounds_distinct_counts(monkeypatch, fake_clock):
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


def test_target_appearing_after_list_failure_still_succeeds(monkeypatch, fake_clock):
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
    assert fake_clock.value == 2


def test_ambiguous_layout_is_still_rejected_without_waiting(monkeypatch, fake_clock):
    targets = [{"type": "page", "url": "https://www.tradingview.com/chart/AbCd1234/"}] * 2
    monkeypatch.setattr(desktop.cdp, "http_json", lambda port, path, timeout=3.0: targets)
    with pytest.raises(CaptureError) as err:
        desktop.wait_for_chart_page(9333, "AbCd1234", timeout=3)
    assert err.value.code == "LAYOUT_NOT_UNIQUE"
    assert fake_clock.value == 0
