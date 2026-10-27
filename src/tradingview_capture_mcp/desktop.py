"""Start, check and stop TradingView Desktop with a loopback-only DevTools port."""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Mapping
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
# Variables an MCP host built on Electron or Node can pass down: ELECTRON_RUN_AS_NODE starts TradingView
# Desktop as plain Node, without a window or debugging port, and the others load code into it.
_APP_UNSAFE_ENV = re.compile(r"^(ELECTRON_|DYLD_|NODE_OPTIONS$|NODE_PATH$)")


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


def already_running(pids: list[int]) -> CaptureError:
    """The error for a TradingView Desktop the user started; it says why and what to do."""
    return CaptureError(
        TV_ALREADY_RUNNING,
        "TradingView Desktop is already running without this tool's debugging port. The tool has to "
        "start it itself and quits it when the batch ends; full screen or not makes no difference. Ask "
        "the user to quit it completely (Cmd+Q; closing the window is not enough) and never kill it, "
        "then retry; capture_retry continues a batch that stopped this way.",
        {"pids": pids},
    )


def app_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment TradingView Desktop starts with: this process's, less what would change how it runs."""
    source = os.environ if environ is None else environ
    return {key: value for key, value in source.items() if not _APP_UNSAFE_ENV.match(key)}


def launch(config: Config, *, startup_timeout: float = 40.0, poll: float = 0.5) -> DesktopSession:
    """Start TradingView Desktop with the DevTools port; refuse to touch a copy the user already runs."""
    if not config.app_binary.is_file():
        raise CaptureError(
            TV_NOT_INSTALLED, "TradingView Desktop was not found", {"app_path": str(config.app_path)}
        )
    pids = running_pids()
    if pids:
        raise already_running(pids)
    if listening_addresses(config.debug_port):
        raise CaptureError(PORT_IN_USE, "the debug port is already in use", {"port": config.debug_port})
    process = subprocess.Popen(
        [str(config.app_binary), f"--remote-debugging-port={config.debug_port}"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=app_environment(),
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
    targets: list[dict[str, Any]] | None = None
    while True:
        try:
            listed = cdp.http_json(port, "/json/list")
            targets = listed
            return cdp.select_chart_page(listed, layout)
        except CaptureError as exc:
            if exc.code != LAYOUT_NOT_FOUND:
                raise
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise layout_not_found(layout, targets, timeout)
        time.sleep(poll)


def layout_not_found(layout: str, targets: list[dict[str, Any]] | None, timeout: float) -> CaptureError:
    """The error for a layout no tab showed in time; it says what the tabs were and what to do."""
    pages = [t for t in targets or [] if isinstance(t, dict) and t.get("type") == "page"]
    detail = {
        "layout": layout,
        "waitedSec": timeout,
        "targetList": targets is not None,
        "pages": len(pages),
        # Tabs that show some other layout: a wrong layout ID, or one the account does not have.
        "chartPages": sum(1 for t in pages if "/chart/" in str(t.get("url", ""))),
    }
    if targets is None:
        return CaptureError(
            LAYOUT_NOT_FOUND, f"the DevTools target list never loaded within {timeout:g}s; try again", detail
        )
    return CaptureError(
        LAYOUT_NOT_FOUND,
        f"TradingView Desktop started but no tab showed this layout within {timeout:g}s. It loads the "
        "layout from TradingView's servers, so a network outage at startup ends here, and so does a layout "
        "ID that is wrong or not in this account (chartPages counts tabs showing other layouts). Check the "
        "network and the layout ID, then try again; capture_retry continues a batch that stopped this way.",
        detail,
    )


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
