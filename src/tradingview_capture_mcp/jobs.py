"""Start capture batches in a background process and report their progress."""

from __future__ import annotations

import contextlib
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from .capture import CaptureRequest, run_capture, validate_request
from .config import Config
from .desktop import already_running, running_pids
from .driver import RealDesktop
from .errors import BATCH_LOCKED, INVALID_ARGUMENT, NOT_FOUND, OUTPUT_EXISTS, CaptureError
from .store import (
    FILE_MODE,
    JOBS_DIR,
    ensure_dir,
    lock_is_held,
    read_json,
    resolve_inside_root,
    stamp,
    write_json_new,
)

_JOB_ID = re.compile(r"[0-9a-f]{32}")


def _jobs_dir(config: Config) -> Path:
    path = config.output_root / JOBS_DIR
    ensure_dir(path)
    return path


def _check_job_id(job_id: str) -> str:
    if not _JOB_ID.fullmatch(job_id or ""):
        raise CaptureError(INVALID_ARGUMENT, "job_id must be 32 hex characters", {})
    return job_id


def _spawn_detached(argv: list[str], log_path: Path) -> int:
    """Start the batch in its own session with output in the job log; no Popen object outlives this call."""
    log = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
    try:
        return os.posix_spawn(
            argv[0],
            argv,
            os.environ,
            file_actions=[
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_DUP2, log, 1),
                (os.POSIX_SPAWN_DUP2, log, 2),
            ],
            setsid=True,
        )
    finally:
        os.close(log)


def start(config: Config, request: CaptureRequest, *, python: str | None = None) -> dict[str, Any]:
    """Validate, then run the batch in a detached process; return at once with the job id."""
    validate_request(request)
    out = resolve_inside_root(config.output_root, request.output_dir)
    if request.retry_failed:
        if not (out / "batch.json").is_file():
            raise CaptureError(NOT_FOUND, "no batch at output_dir", {"output_dir": str(out)})
        manifest = out / "capture-manifest.json"
        if manifest.is_file() and all(
            s.get("status") == "ok" for s in read_json(manifest).get("symbols", [])
        ):
            raise CaptureError(
                NOT_FOUND,
                "nothing left to retry: every symbol already has a capture",
                {"output_dir": str(out)},
            )
    elif out.exists():
        raise CaptureError(OUTPUT_EXISTS, "output_dir already exists", {"output_dir": str(out)})
    if lock_is_held(config.output_root):
        raise CaptureError(BATCH_LOCKED, "another capture is running", {})
    # Say so now, before a job or output_dir exists, not later from a background job.
    pids = running_pids()
    if pids:
        raise already_running(pids)
    job_id = uuid.uuid4().hex
    folder = _jobs_dir(config)
    write_json_new(folder / f"{job_id}.request.json", request.to_dict())
    argv = [python or sys.executable, "-m", "tradingview_capture_mcp.cli", "run-job", "--job-id", job_id]
    pid = _spawn_detached(argv, folder / f"{job_id}.log")
    write_json_new(
        folder / f"{job_id}.json",
        {"jobId": job_id, "pid": pid, "outputDir": str(out), "startedAt": stamp()},
    )
    return {"jobId": job_id, "outputDir": str(out), "pid": pid}


def retry_request(config: Config, output_dir: str) -> CaptureRequest:
    out = resolve_inside_root(config.output_root, output_dir)
    batch = out / "batch.json"
    if not batch.is_file():
        raise CaptureError(NOT_FOUND, "no batch at output_dir", {"output_dir": str(out)})
    raw = dict(read_json(batch)["request"])
    raw.update(output_dir=str(out), retry_failed=True)
    return CaptureRequest.from_dict(raw)


def retry(config: Config, output_dir: str, *, python: str | None = None) -> dict[str, Any]:
    return start(config, retry_request(config, output_dir), python=python)


def _alive(pid: int) -> bool:
    with contextlib.suppress(ChildProcessError):
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False  # our own child, and it has exited
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def status(config: Config, *, job_id: str | None = None, output_dir: str | None = None) -> dict[str, Any]:
    if job_id:
        _check_job_id(job_id)
        index_path = config.output_root / JOBS_DIR / f"{job_id}.json"
        if not index_path.is_file():
            raise CaptureError(NOT_FOUND, "unknown job", {"job_id": job_id})
        index = read_json(index_path)
        out, pid = Path(index["outputDir"]), int(index["pid"])
    elif output_dir:
        out, pid = resolve_inside_root(config.output_root, output_dir), None
    else:
        raise CaptureError(INVALID_ARGUMENT, "pass job_id or output_dir", {})
    job_path = out / "job.json"
    job: dict[str, Any] = read_json(job_path) if job_path.is_file() else {}
    if not job or (job_id and job.get("jobId") != job_id):
        job = {"jobId": job_id, "state": "starting", "outputDir": str(out)}  # the child has not written yet
    pid = pid or job.get("pid")
    if job.get("state") in ("running", "starting") and pid and not _alive(int(pid)):
        job["state"] = "crashed"
        job["log"] = str(config.output_root / JOBS_DIR / f"{job.get('jobId')}.log")
    return job


def run_job(config: Config, job_id: str) -> dict[str, Any]:
    """Body of the background process that start() launches."""
    request = CaptureRequest.from_dict(
        read_json(config.output_root / JOBS_DIR / f"{_check_job_id(job_id)}.request.json")
    )
    return run_capture(
        request, config, job_id=job_id, desktop=RealDesktop(config, request.layout), pid=os.getpid()
    )
