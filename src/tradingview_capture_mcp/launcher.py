"""A double-clickable macOS app that opens TradingView Desktop with this tool's debugging port."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .errors import INTERNAL_ERROR, INVALID_ARGUMENT, OUTPUT_EXISTS, CaptureError

OSACOMPILE = "/usr/bin/osacompile"
DEFAULT_PATH = Path.home() / "Applications" / "TradingView Capture.app"
TITLE = "TradingView Capture"
FAILED = (
    "没能带采集用的调试端口打开 TradingView。"
    " / TradingView Desktop could not be opened with the capture debugging port."
)


def _string(text: str) -> str:
    """An AppleScript string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def script(command: Path) -> list[str]:
    """The app's AppleScript: run `<command> open`, and show the user why when it fails."""
    return [
        "try",
        # The report goes to stderr, which is what AppleScript hands over when the command fails.
        f'do shell script quoted form of {_string(str(command))} & " open 1>&2"',
        "on error message",
        f"display dialog {_string(FAILED)} & return & return & message "
        f'buttons {{"OK"}} default button 1 with title {_string(TITLE)}',
        "end try",
    ]


def install(target: Path, command: Path) -> dict[str, Any]:
    """Make the app at `target`; it runs `command open`. Never replaces anything already there."""
    target = target.expanduser()
    if target.suffix != ".app":
        raise CaptureError(INVALID_ARGUMENT, "the launcher path must end in .app", {"path": str(target)})
    if target.exists() or target.is_symlink():
        raise CaptureError(
            OUTPUT_EXISTS,
            "something is already at the launcher path; move it away first",
            {"path": str(target)},
        )
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)  # ~/Applications may not exist yet
    argv = [OSACOMPILE, "-o", str(target)]
    for line in script(command):
        argv += ["-e", line]
    result = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=60)
    if result.returncode != 0:
        raise CaptureError(
            INTERNAL_ERROR, "osacompile could not make the launcher", {"returncode": result.returncode}
        )
    return {"path": str(target), "command": str(command)}
