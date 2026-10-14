import signal
import subprocess
import sys
import time

import pytest

from tradingview_capture_mcp import driver, signals

SCRIPT = """
import sys, time
from pathlib import Path
from tradingview_capture_mcp.signals import exit_on_termination
marker = Path(sys.argv[1])
with exit_on_termination():
    try:
        marker.write_text("started")
        time.sleep(30)
    finally:
        marker.write_text("cleaned")
"""


@pytest.mark.parametrize("signum", [signal.SIGTERM, signal.SIGHUP])
def test_termination_signals_run_cleanup_code(tmp_path, signum):
    marker = tmp_path / "marker"
    process = subprocess.Popen([sys.executable, "-c", SCRIPT, str(marker)])
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    process.send_signal(signum)
    assert process.wait(timeout=10) == 128 + signum
    assert marker.read_text() == "cleaned"


def test_the_server_handler_stops_desktops_before_exiting(monkeypatch):
    stopped = []
    monkeypatch.setattr(signals, "stop_all_desktops", lambda: stopped.append(True))
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        signals.install_server_handlers()
        handler = signal.getsignal(signal.SIGTERM)
        with pytest.raises(SystemExit) as exit_info:
            handler(signal.SIGTERM, None)
        assert exit_info.value.code == 128 + signal.SIGTERM
        assert stopped == [True]
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def test_stop_all_desktops_stops_every_registered_desktop():
    class Dummy:
        def __init__(self):
            self.stopped = 0

        def stop(self):
            self.stopped += 1
            driver._ACTIVE.discard(self)

    first, second = Dummy(), Dummy()
    driver._ACTIVE.update({first, second})
    driver.stop_all_desktops()
    assert (first.stopped, second.stopped) == (1, 1)
    assert not driver._ACTIVE
