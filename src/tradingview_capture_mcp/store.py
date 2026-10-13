"""Owner-only, create-only file writes, output-root checks and the batch lock."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import BATCH_LOCKED, INVALID_ARGUMENT, OUTPUT_EXISTS, OUTPUT_OUTSIDE_ROOT, CaptureError

FILE_MODE = 0o600
DIR_MODE = 0o700
LOCK_NAME = ".tradingview-capture.lock"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]
    os.fsync(fd)


def write_new(path: Path, data: bytes) -> str:
    """Create `path` with mode 0600 and return the SHA-256 of `data`; never overwrite."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    except FileExistsError as exc:
        raise CaptureError(OUTPUT_EXISTS, f"refusing to overwrite {path.name}", {"path": str(path)}) from exc
    try:
        _write_all(fd, data)
    finally:
        os.close(fd)
    return sha256_bytes(data)


def dumps_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json_new(path: Path, value: Any) -> str:
    return write_new(path, dumps_json(value))


def replace_json(path: Path, value: Any) -> None:
    """Atomically replace a progress file; the only kind of file this tool rewrites."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        _write_all(fd, dumps_json(value))
    finally:
        os.close(fd)
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def make_dir_new(path: Path) -> None:
    try:
        path.mkdir(mode=DIR_MODE)
    except FileExistsError as exc:
        raise CaptureError(OUTPUT_EXISTS, f"{path.name} already exists", {"path": str(path)}) from exc
    os.chmod(path, DIR_MODE)


def ensure_dir(path: Path) -> None:
    path.mkdir(mode=DIR_MODE, exist_ok=True)
    os.chmod(path, DIR_MODE)


def resolve_inside_root(root: Path, value: str | Path) -> Path:
    """Resolve an absolute path whose parent exists inside `root`; the leaf may not exist yet."""
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() or candidate.name in ("", ".", ".."):
        raise CaptureError(INVALID_ARGUMENT, "the path must be absolute", {"path": str(value)})
    try:
        parent = candidate.parent.resolve(strict=True)
    except FileNotFoundError as exc:
        raise CaptureError(INVALID_ARGUMENT, "the parent directory must exist", {"path": str(value)}) from exc
    resolved = parent / candidate.name
    real_root = root.resolve()
    if parent != real_root and real_root not in parent.parents:
        raise CaptureError(
            OUTPUT_OUTSIDE_ROOT, "the path must be inside the output root", {"path": str(resolved)}
        )
    if resolved.is_symlink():
        raise CaptureError(OUTPUT_OUTSIDE_ROOT, "the path must not be a symlink", {"path": str(resolved)})
    return resolved


def safe_name(code: str) -> str:
    """Folder name for a TradingView code, e.g. BINANCE:BTCUSDT.P -> BINANCE_BTCUSDT.P."""
    return _UNSAFE.sub("_", code)


def stamp(moment: datetime | None = None) -> dict[str, Any]:
    """A timestamp in both forms the outputs use: local ISO 8601 with offset, and UNIX seconds."""
    moment = moment or datetime.now().astimezone()
    return {"iso": moment.isoformat(timespec="milliseconds"), "unix": round(moment.timestamp(), 3)}


class BatchLock:
    """One capture at a time per output root, held with flock for the whole batch."""

    def __init__(self, root: Path) -> None:
        self.path = root / LOCK_NAME
        self._fd: int | None = None

    def acquire(self) -> None:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise CaptureError(BATCH_LOCKED, "another capture is running", {"lock": str(self.path)}) from exc
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> BatchLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def lock_is_held(root: Path) -> bool:
    lock = BatchLock(root)
    try:
        lock.acquire()
    except CaptureError:
        return True
    lock.release()
    return False
