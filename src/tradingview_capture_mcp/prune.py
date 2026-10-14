"""Keep the current day's capture batches and move older ones to the macOS Trash.

Nothing is deleted for good: folders go to the Trash with the system's /usr/bin/trash (macOS 15 or later),
so the user can put any of them back until the Trash is emptied, and the disk space returns when it is."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import TOOL_NAME
from .config import Config
from .errors import INVALID_ARGUMENT, TRASH_FAILED, TRASH_UNAVAILABLE, CaptureError
from .store import BatchLock, read_json

TRASH_COMMAND = Path("/usr/bin/trash")
MAX_KEEP_DAYS = 365
# Batches sit a few folders below the root (for example <project>/<day>/capture); this bounds the walk.
MAX_DEPTH = 8
NOTE = (
    "Folders go to the macOS Trash and nothing is deleted for good; the space returns when the user empties "
    "the Trash. Files a caller made from a capture outside its batch folder follow the caller's own rules."
)


def require_trash_command() -> None:
    if not TRASH_COMMAND.is_file():
        raise CaptureError(
            TRASH_UNAVAILABLE,
            "the system trash command is missing (macOS 15 or later has /usr/bin/trash); nothing was moved",
            {"command": str(TRASH_COMMAND)},
        )


def move_to_trash(path: Path) -> None:
    """Hand one folder to the system's trash command; a folder still in place afterwards is an error."""
    require_trash_command()
    result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        [str(TRASH_COMMAND), str(path)], capture_output=True, text=True, check=False, timeout=300
    )
    if result.returncode != 0 or path.exists():
        raise CaptureError(
            TRASH_FAILED,
            "the Trash did not take the folder; it is still in place",
            {"path": str(path), "returncode": result.returncode, "stderr": result.stderr[-300:]},
        )


def _tool_batch(folder: Path) -> bool:
    try:
        record = read_json(folder / "batch.json")
    except (OSError, ValueError):
        return False
    return isinstance(record, dict) and (record.get("tool") or {}).get("name") == TOOL_NAME


def find_batches(root: Path) -> list[Path]:
    """This tool's batch folders under the root: never follows symlinks, never looks inside a batch."""
    found: list[Path] = []
    pending = [(root, 0)]
    while pending:
        folder, depth = pending.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        if folder != root and any(e.name == "batch.json" for e in entries) and _tool_batch(folder):
            found.append(folder)
            continue
        if depth >= MAX_DEPTH:
            continue
        for entry in entries:
            if not entry.name.startswith(".") and entry.is_dir(follow_symlinks=False):
                pending.append((Path(entry.path), depth + 1))
    return sorted(found)


def _unix(record: Any, *keys: str) -> float | None:
    for key in keys:
        if not isinstance(record, dict):
            return None
        record = record.get(key)
    return float(record) if isinstance(record, int | float) else None


def batch_day(folder: Path, zone: Any) -> date | None:
    """The day a batch last did anything: the latest of its start, its last finish and its last progress."""
    times = []
    for name, keys in (
        ("batch.json", ("startedAt", "unix")),
        ("capture-manifest.json", ("finishedAt", "unix")),
        ("job.json", ("updatedAt", "unix")),
    ):
        try:
            value = _unix(read_json(folder / name), *keys)
        except (OSError, ValueError):
            value = None
        if value is not None:
            times.append(value)
    return datetime.fromtimestamp(max(times), zone).date() if times else None


def folder_bytes(folder: Path) -> int:
    total = 0
    for current, _dirs, files in os.walk(folder, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(current, name)).st_size
            except OSError:
                continue
    return total


def prune(
    config: Config,
    *,
    keep_days: int = 1,
    apply: bool = False,
    now: datetime | None = None,
    trash: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """List (or, with apply, move to the Trash) every batch whose last activity was before the days kept."""
    if not 1 <= keep_days <= MAX_KEEP_DAYS:
        raise CaptureError(INVALID_ARGUMENT, f"keep_days must be between 1 and {MAX_KEEP_DAYS}", {})
    moment = now or datetime.now().astimezone()
    today = moment.date()
    keep_from = today - timedelta(days=keep_days - 1)
    root = config.output_root.resolve()
    move = trash or move_to_trash
    lock = BatchLock(config.output_root) if apply else None
    if apply and trash is None:
        require_trash_command()  # before anything moves
    if lock:
        lock.acquire()  # no capture starts while folders move; a running one makes this BATCH_LOCKED
    try:
        batches = []
        for folder in find_batches(root):
            day = batch_day(folder, moment.tzinfo)
            entry: dict[str, Any] = {
                "path": str(folder.relative_to(root)),
                "day": day.isoformat() if day else None,
                "bytes": folder_bytes(folder),
            }
            if day is None:
                entry.update(action="keep", reason="no readable date")
            elif day >= keep_from:
                entry["action"] = "keep"
            elif not apply:
                entry["action"] = "wouldTrash"
            else:
                try:
                    move(folder)
                    entry["action"] = "trashed"
                except CaptureError as exc:
                    entry.update(action="failed", error=exc.to_dict())
            batches.append(entry)
    finally:
        if lock:
            lock.release()
    count = {action: sum(1 for b in batches if b["action"] == action) for action in ("keep", "wouldTrash")}
    return {
        "outputRoot": str(root),
        "today": today.isoformat(),
        "keepFrom": keep_from.isoformat(),
        "keepDays": keep_days,
        "apply": apply,
        "batches": batches,
        "totals": {
            "kept": count["keep"],
            "wouldTrash": count["wouldTrash"],
            "trashed": sum(1 for b in batches if b["action"] == "trashed"),
            "failed": sum(1 for b in batches if b["action"] == "failed"),
            "bytesToFree": sum(b["bytes"] for b in batches if b["action"] in ("wouldTrash", "trashed")),
        },
        "note": NOTE,
    }
