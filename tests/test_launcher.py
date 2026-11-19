import subprocess
import sys

import pytest

from tradingview_capture_mcp import launcher
from tradingview_capture_mcp.errors import CaptureError

macos = pytest.mark.skipif(sys.platform != "darwin", reason="osacompile and osascript exist only on macOS")


def fake_program(folder):
    """Stands in for tradingview-capture: records how it was called."""
    folder.mkdir(parents=True)
    program = folder / "tradingview-capture"
    program.write_text('#!/bin/sh\nprintf "%s" "$*" > "$(dirname "$0")/called"\n', encoding="utf-8")
    program.chmod(0o700)
    return program


@macos
def test_the_launcher_opens_tradingview_through_the_program_that_made_it(tmp_path):
    # Quotes and spaces in the path must survive both the AppleScript string and the shell.
    program = fake_program(tmp_path / 'a "quoted" folder\'s name')
    report = launcher.install(tmp_path / "Open TV.app", program)
    assert report == {"path": str(tmp_path / "Open TV.app"), "command": str(program)}
    script = tmp_path / "Open TV.app" / "Contents" / "Resources" / "Scripts" / "main.scpt"
    subprocess.run(["/usr/bin/osascript", str(script)], check=True, timeout=30)
    assert (program.parent / "called").read_text() == "open"


def test_an_existing_app_is_never_replaced(tmp_path):
    (tmp_path / "Open TV.app").mkdir()
    with pytest.raises(CaptureError) as err:
        launcher.install(tmp_path / "Open TV.app", tmp_path / "tradingview-capture")
    assert err.value.code == "OUTPUT_EXISTS"


def test_the_launcher_must_be_an_app(tmp_path):
    with pytest.raises(CaptureError) as err:
        launcher.install(tmp_path / "Open TV", tmp_path / "tradingview-capture")
    assert err.value.code == "INVALID_ARGUMENT"
