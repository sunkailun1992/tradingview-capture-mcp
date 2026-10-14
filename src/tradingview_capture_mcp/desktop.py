"""Start, check and stop TradingView Desktop with a loopback-only DevTools port."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from . import cdp
from .config import Config
from .errors import (
    CDP_NOT_LOCAL,
    LAYOUT_NOT_FOUND,
    PORT_IN_USE,
    TV_ALREADY_RUNNING,
    TV_NOT_INSTALLED,
    TV_STARTUP_TIMEOUT,
    CaptureError,
)

LOCAL_ADDRESSES = {"127.0.0.1", "[::1]", "localhost"}
_TV_VERSION = re.compile(r"TVDesktop/(\S+)")


@dataclass
class DesktopSession:
    process: subprocess.Popen
    port: int
    version: str
    browser: str

    @property
    def pid(self) -> int:
        return self.process.pid


def running_pids(process_name: str = "TradingView") -> list[int]:
    result = subprocess.run(
        ["/usr/bin/pgrep", "-x", process_name], capture_output=True, text=True, check=False
    )
    return [int(pid) for pid in result.stdout.split()]


def listening_addresses(port: int) -> list[str]:
    result = subprocess.run(
        ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "n"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line[1:].rsplit(":", 1)[0] for line in result.stdout.splitlines() if line.startswith("n")]


def parse_version(info: dict[str, Any]) -> str:
    match = _TV_VERSION.search(str(info.get("User-Agent", "")))
    return match.group(1) if match else "unknown"


def launch(config: Config, *, startup_timeout: float = 40.0, poll: float = 0.5) -> DesktopSession:
    """Start TradingView Desktop with the DevTools port; refuse to touch a copy the user already runs."""
    if not config.app_binary.is_file():
        raise CaptureError(
            TV_NOT_INSTALLED, "TradingView Desktop was not found", {"app_path": str(config.app_path)}
        )
    pids = running_pids()
    if pids:
        raise CaptureError(
            TV_ALREADY_RUNNING,
            "TradingView Desktop is already running without this tool's debugging port. The tool has to "
            "start it itself and quits it when the batch ends; full screen or not makes no difference. Ask "
            "the user to quit it completely (Cmd+Q; closing the window is not enough) and never kill it, "
            "then retry; capture_retry continues a batch that stopped this way.",
            {"pids": pids},
        )
    if listening_addresses(config.debug_port):
        raise CaptureError(PORT_IN_USE, "the debug port is already in use", {"port": config.debug_port})
    process = subprocess.Popen(
        [str(config.app_binary), f"--remote-debugging-port={config.debug_port}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        info = _wait_for_devtools(process, config.debug_port, startup_timeout, poll)
        addresses = listening_addresses(config.debug_port)
        if not addresses or any(address not in LOCAL_ADDRESSES for address in addresses):
            raise CaptureError(
                CDP_NOT_LOCAL, "the debug port must listen on loopback only", {"addresses": addresses}
            )
        return DesktopSession(
            process=process,
            port=config.debug_port,
            version=parse_version(info),
            browser=str(info.get("Browser", "")),
        )
    except BaseException:
        stop_process(process)
        raise


def _wait_for_devtools(process: subprocess.Popen, port: int, timeout: float, poll: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CaptureError(
                TV_STARTUP_TIMEOUT,
                "TradingView Desktop exited during startup",
                {"returncode": process.returncode},
            )
        try:
            return cdp.http_json(port, "/json/version", timeout=2.0)
        except (OSError, ValueError):
            time.sleep(poll)
    raise CaptureError(TV_STARTUP_TIMEOUT, f"DevTools did not answer within {timeout:g}s", {"port": port})


def wait_for_chart_page(
    port: int, layout: str, *, timeout: float = 60.0, poll: float = 1.0
) -> dict[str, Any]:
    """Wait until the restored tab for `layout` is listed, then return its DevTools target."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return cdp.select_chart_page(cdp.http_json(port, "/json/list"), layout)
        except CaptureError as exc:
            if exc.code != LAYOUT_NOT_FOUND or time.monotonic() >= deadline:
                raise
        except (OSError, ValueError) as exc:
            if time.monotonic() >= deadline:
                raise CaptureError(
                    LAYOUT_NOT_FOUND, "the DevTools target list never loaded", {"layout": layout}
                ) from exc
        time.sleep(poll)


def stop_process(process: subprocess.Popen, *, timeout: float = 20.0) -> None:
    """Stop only the process this tool started: SIGTERM first, SIGKILL after the timeout."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)
