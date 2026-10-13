import socket
import stat
import subprocess
import sys

import pytest

from tradingview_capture_mcp import desktop
from tradingview_capture_mcp.config import Config
from tradingview_capture_mcp.errors import CaptureError

FAKE_APP = """import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
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
HTTPServer(("127.0.0.1", port), Handler).serve_forever()
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
    binary.write_text(f"#!{sys.executable}\n" + FAKE_APP, encoding="utf-8")
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


def test_refuses_when_tradingview_already_runs(fake_app, monkeypatch):
    monkeypatch.setattr(desktop, "running_pids", lambda process_name="TradingView": [4242])
    with pytest.raises(CaptureError) as err:
        desktop.launch(fake_app)
    assert err.value.code == "TV_ALREADY_RUNNING"


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
