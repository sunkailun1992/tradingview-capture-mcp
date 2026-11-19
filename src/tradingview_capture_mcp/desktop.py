"""Find, start and let go of TradingView Desktop with a loopback-only DevTools port.

A TradingView Desktop that already runs with this tool's port is used as it is and never quit, so the user can
keep it open; one that runs without the port cannot be reached and is never touched."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
import urllib.error
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
# macOS's own way to open an app (LaunchServices): a TradingView left open is then an app of the user's
# session like any other, not a child of whichever process happened to start a batch.
OPEN = "/usr/bin/open"
# A chart in a background tab, or in a window other windows cover, otherwise gets its timers slowed to one
# wake-up a second, and after five minutes to one a minute; the readiness waits would time out.
APP_SWITCHES = (
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
)
_TV_VERSION = re.compile(r"TVDesktop/(\S+)")
# Variables an MCP host built on Electron or Node can pass down: ELECTRON_RUN_AS_NODE starts TradingView
# Desktop as plain Node, without a window or debugging port, and the others load code into it.
_APP_UNSAFE_ENV = re.compile(r"^(ELECTRON_|DYLD_|NODE_OPTIONS$|NODE_PATH$)")


@dataclass
class DesktopSession:
    port: int
    version: str
    browser: str
    pid: int | None = None  # the TradingView Desktop process that serves the port
    launched: bool = False  # this tool started it; otherwise it was already open
    # Held only for a TradingView this tool started to quit again at the end (keep_open = false).
    process: subprocess.Popen | None = None


def running_pids(process_name: str = "TradingView") -> list[int]:
    result = subprocess.run(
        ["/usr/bin/pgrep", "-x", process_name], capture_output=True, text=True, check=False
    )
    return [int(pid) for pid in result.stdout.split()]


def listeners(port: int) -> list[tuple[int, str]]:
    """(pid, address) of every socket listening on the port."""
    result = subprocess.run(
        ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "pn"],
        capture_output=True,
        text=True,
        check=False,
    )
    found: list[tuple[int, str]] = []
    pid: int | None = None
    for line in result.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            found.append((pid, line[1:].rsplit(":", 1)[0]))
    return found


def listening_addresses(port: int) -> list[str]:
    return [address for _, address in listeners(port)]


def parse_version(info: dict[str, Any]) -> str:
    match = _TV_VERSION.search(str(info.get("User-Agent", "")))
    return match.group(1) if match else "unknown"


def already_running(pids: list[int], port: int) -> CaptureError:
    """The error for a TradingView Desktop opened without this tool's port; it says why and what to do."""
    return CaptureError(
        TV_ALREADY_RUNNING,
        "TradingView Desktop is running without this tool's debugging port (opened from the Dock, Finder or "
        "Spotlight), so the tool cannot use it; full screen or not makes no difference. Ask the user to quit "
        "it completely (Cmd+Q; closing the window is not enough) and never kill it. Then either open it "
        "again with the port (the TradingView Capture launcher, `tradingview-capture open` or the "
        "desktop_open tool) or leave it closed and let the next capture start it; it stays open afterwards. "
        "Then retry; capture_retry continues a batch that stopped this way.",
        {"pids": pids, "port": port},
    )


def app_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment TradingView Desktop starts with: this process's, less what would change how it runs."""
    source = os.environ if environ is None else environ
    return {key: value for key, value in source.items() if not _APP_UNSAFE_ENV.match(key)}


def launch_arguments(port: int) -> list[str]:
    return [f"--remote-debugging-port={port}", *APP_SWITCHES]


def attachable(config: Config) -> int | None:
    """The TradingView Desktop process that serves DevTools on the configured port, or None when none runs.

    Raises when TradingView Desktop runs but cannot be used, or another program holds the port; it never
    waits, so a capture can say so before it creates anything."""
    pids = running_pids()
    found = listeners(config.debug_port)
    if not pids:
        if found:
            raise CaptureError(PORT_IN_USE, "the debug port is already in use", {"port": config.debug_port})
        return None
    served = [pid for pid, _ in found if pid in pids]
    if not served:
        raise already_running(pids, config.debug_port)
    addresses = [address for _, address in found]
    if any(address not in LOCAL_ADDRESSES for address in addresses):
        # It is the user's TradingView: refuse it, but never stop it.
        raise CaptureError(
            CDP_NOT_LOCAL,
            "TradingView Desktop's debugging port listens beyond loopback; ask the user to quit it (Cmd+Q) "
            "and open it again with `tradingview-capture open`",
            {"addresses": addresses},
        )
    return served[0]


def connect_or_launch(config: Config, *, startup_timeout: float = 40.0, poll: float = 0.5) -> DesktopSession:
    """Use the TradingView Desktop that runs with the port, or start one; never touch one without the port."""
    pid = attachable(config)
    if pid is None:
        return _launch(config, startup_timeout=startup_timeout, poll=poll)
    info = _wait_for_devtools(None, config.debug_port, startup_timeout, poll)
    return DesktopSession(
        port=config.debug_port,
        version=parse_version(info),
        browser=str(info.get("Browser", "")),
        pid=pid,
        launched=False,
    )


def _launch(
    config: Config,
    *,
    keep_open: bool | None = None,
    foreground: bool = False,
    startup_timeout: float = 40.0,
    poll: float = 0.5,
) -> DesktopSession:
    """Start TradingView Desktop with the DevTools port; only after attachable() found none running.

    To stay open (keep_open, the default) it is opened the way macOS opens apps and this tool holds nothing
    of it; otherwise this tool starts it as its own child so that release() can quit it again."""
    if not config.app_binary.is_file():
        raise CaptureError(
            TV_NOT_INSTALLED, "TradingView Desktop was not found", {"app_path": str(config.app_path)}
        )
    stays_open = config.keep_open if keep_open is None else keep_open
    port = config.debug_port
    if stays_open:
        _open_app(config, launch_arguments(port), foreground=foreground)
        info = _wait_for_devtools(None, port, startup_timeout, poll)
        pids = running_pids()
        try:
            pid = _serving_pid(port, pids)
        except CaptureError as exc:
            if exc.code == CDP_NOT_LOCAL:
                # The copy just opened holds the port; nothing else ran when it was asked for, so stop it.
                for holder in {holder for holder, _ in listeners(port) if holder in pids}:
                    os.kill(holder, signal.SIGTERM)
            raise
        return DesktopSession(
            port=port,
            version=parse_version(info),
            browser=str(info.get("Browser", "")),
            pid=pid,
            launched=True,
        )
    process = subprocess.Popen(
        [str(config.app_binary), *launch_arguments(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=app_environment(),
    )
    try:
        info = _wait_for_devtools(process, port, startup_timeout, poll)
        _serving_pid(port, [process.pid])
        return DesktopSession(
            port=port,
            version=parse_version(info),
            browser=str(info.get("Browser", "")),
            pid=process.pid,
            launched=True,
            process=process,
        )
    except BaseException:
        stop_process(process)
        raise


def release(session: DesktopSession) -> None:
    """Let go of TradingView Desktop: quit it only when this tool started it to quit at the end."""
    if session.process is not None:
        stop_process(session.process)


def open_for_user(config: Config, *, startup_timeout: float = 40.0, poll: float = 0.5) -> dict[str, Any]:
    """Open TradingView Desktop in front with the port for the user to keep using, or bring it forward."""
    pid = attachable(config)
    if pid is None:
        session = _launch(config, keep_open=True, foreground=True, startup_timeout=startup_timeout, poll=poll)
        return {"state": "started", "port": session.port, "pid": session.pid, "version": session.version}
    info = _wait_for_devtools(None, config.debug_port, startup_timeout, poll)
    _open_app(config, None, foreground=True)  # an app already running only comes to the front
    return {"state": "running", "port": config.debug_port, "pid": pid, "version": parse_version(info)}


def _open_app(config: Config, arguments: list[str] | None, *, foreground: bool) -> None:
    argv = [OPEN, *(() if foreground else ("-g",)), "-a", str(config.app_path)]
    if arguments:
        argv += ["--args", *arguments]
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=app_environment(),
    )
    if result.returncode != 0:
        raise CaptureError(
            TV_STARTUP_TIMEOUT, "macOS could not open TradingView Desktop", {"returncode": result.returncode}
        )


def _serving_pid(port: int, pids: list[int]) -> int:
    """The process among `pids` that serves the port; every address on the port must be loopback."""
    found = listeners(port)
    served = [pid for pid, _ in found if pid in pids]
    if not served:
        raise CaptureError(PORT_IN_USE, "another program holds the debug port", {"port": port})
    addresses = [address for _, address in found]
    if any(address not in LOCAL_ADDRESSES for address in addresses):
        raise CaptureError(
            CDP_NOT_LOCAL, "the debug port must listen on loopback only", {"addresses": addresses}
        )
    return served[0]


def _wait_for_devtools(
    process: subprocess.Popen | None, port: int, timeout: float, poll: float
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise CaptureError(
                TV_STARTUP_TIMEOUT,
                "TradingView Desktop exited during startup",
                {"returncode": process.returncode},
            )
        try:
            return cdp.http_json(port, "/json/version", timeout=2.0)
        except (OSError, ValueError):
            time.sleep(poll)
    if process is None:
        pids = running_pids()
        if pids and not any(pid in pids for pid, _ in listeners(port)):
            # macOS brings an app that already runs to the front and drops the arguments: the user opened
            # TradingView meanwhile, without the port.
            raise already_running(pids, port)
    raise CaptureError(TV_STARTUP_TIMEOUT, f"DevTools did not answer within {timeout:g}s", {"port": port})


def wait_for_chart_page(
    port: int, layout: str, *, timeout: float = 60.0, poll: float = 1.0
) -> dict[str, Any]:
    """Wait until the restored tab for `layout` is listed, then return its DevTools target."""
    deadline = time.monotonic() + timeout
    targets: list[dict[str, Any]] | None = None
    observation: dict[str, Any] = {
        "polls": 0,
        "targetListReads": 0,
        "targetListErrors": {},
        "pageCounts": [],
        "chartPageCounts": [],
        "countsTruncated": False,
    }
    while True:
        observation["polls"] += 1
        try:
            listed = cdp.http_json(port, "/json/list")
            targets = listed
            observation["targetListReads"] += 1
            pages = [t for t in listed if isinstance(t, dict) and t.get("type") == "page"]
            counts = {
                "pageCounts": len(pages),
                "chartPageCounts": sum("/chart/" in str(t.get("url", "")) for t in pages),
            }
            # Only bounded counts survive a failure; target IDs, URLs and contents never do.
            for name, count in counts.items():
                if count not in observation[name]:
                    if len(observation[name]) < 8:
                        observation[name].append(count)
                    else:
                        observation["countsTruncated"] = True
            return cdp.select_chart_page(listed, layout)
        except CaptureError as exc:
            if exc.code != LAYOUT_NOT_FOUND:
                raise
        except (OSError, ValueError) as exc:
            if isinstance(exc, urllib.error.HTTPError):
                kind = "http"
            elif isinstance(exc, TimeoutError) or (
                isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)
            ):
                kind = "timeout"
            elif isinstance(exc, ValueError):
                kind = "invalidResponse"
            else:
                kind = "transport"
            errors = observation["targetListErrors"]
            errors[kind] = errors.get(kind, 0) + 1
        if time.monotonic() >= deadline:
            raise layout_not_found(layout, targets, timeout, target_observation=observation)
        time.sleep(poll)


def layout_not_found(
    layout: str,
    targets: list[dict[str, Any]] | None,
    timeout: float,
    *,
    target_observation: dict[str, Any] | None = None,
) -> CaptureError:
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
    if target_observation is not None:
        detail["targetObservation"] = target_observation
    if targets is None:
        return CaptureError(
            LAYOUT_NOT_FOUND, f"the DevTools target list never loaded within {timeout:g}s; try again", detail
        )
    return CaptureError(
        LAYOUT_NOT_FOUND,
        f"No TradingView Desktop tab showed this layout within {timeout:g}s. If TradingView was already "
        "open, ask the user to open this layout in one of its tabs. A TradingView that just started loads "
        "the layout from TradingView's servers, so a network outage at startup ends here, and so does a "
        "layout ID that is wrong or not in this account (chartPages counts tabs showing other layouts). "
        "Check the network and the layout ID, then try again; capture_retry continues a batch that stopped "
        "this way.",
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
