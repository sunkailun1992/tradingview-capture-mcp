"""Run one capture batch: switch, wait, extract, screenshot and write every symbol."""

from __future__ import annotations

import base64
import binascii
import contextlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import TOOL_NAME, __version__
from .config import Config
from .diagnostics import wait_for_internals
from .driver import ChartDriver, DesktopControl, DesktopInfo
from .errors import (
    CDP_ERROR,
    INTERNAL_ERROR,
    INTERRUPTED,
    INVALID_ARGUMENT,
    NOT_FOUND,
    OUTPUT_EXISTS,
    STUDY_MISSING,
    SYMBOL_NOT_FOUND,
    TV_INTERNALS_CHANGED,
    CaptureError,
)
from .images import png_size
from .readiness import ReadySnapshot, judge, normalize_resolution, wait_until_ready
from .store import (
    BatchLock,
    dumps_json,
    ensure_dir,
    make_dir_new,
    read_json,
    replace_json,
    resolve_inside_root,
    safe_name,
    sha256_bytes,
    stamp,
    write_json_new,
    write_new,
)
from .validation import SYMBOL_RE, TIMEFRAME_RE, check_layout, same_symbol

CAPTURE_METHOD = "CDP_DESKTOP"
PNG_SOURCE = "TradingViewApi.takeClientScreenshot"
CSV_SOURCE = "generated from the chart series in the column order of TradingView's own export"
MAX_SYMBOLS = 500
MAX_RESWITCHES = 3


@dataclass(frozen=True)
class CaptureRequest:
    layout: str
    symbols: tuple[str, ...]
    timeframe: str
    output_dir: str
    required_studies: tuple[str, ...] = ()
    ready_timeout_sec: float = 60.0
    retry_failed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout": self.layout,
            "symbols": list(self.symbols),
            "timeframe": self.timeframe,
            "output_dir": self.output_dir,
            "required_studies": list(self.required_studies),
            "ready_timeout_sec": self.ready_timeout_sec,
            "retry_failed": self.retry_failed,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CaptureRequest:
        try:
            return cls(
                layout=str(raw["layout"]),
                symbols=tuple(str(s) for s in raw["symbols"]),
                timeframe=str(raw["timeframe"]),
                output_dir=str(raw["output_dir"]),
                required_studies=tuple(str(s) for s in raw.get("required_studies") or ()),
                ready_timeout_sec=float(raw.get("ready_timeout_sec", 60.0)),
                retry_failed=bool(raw.get("retry_failed", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CaptureError(INVALID_ARGUMENT, f"invalid capture request: {exc}", {}) from exc


def validate_request(request: CaptureRequest) -> None:
    def bad(message: str, **detail: Any) -> None:
        raise CaptureError(INVALID_ARGUMENT, message, detail)

    check_layout(request.layout)
    if not request.symbols:
        bad("symbols must not be empty")
    if len(request.symbols) > MAX_SYMBOLS:
        bad(f"at most {MAX_SYMBOLS} symbols per batch")
    if len(set(request.symbols)) != len(request.symbols):
        bad("symbols must be unique")
    for code in request.symbols:
        if not SYMBOL_RE.fullmatch(code):
            bad("a symbol must be a TradingView code such as EXCHANGE:TICKER", symbol=code)
    if len({safe_name(code) for code in request.symbols}) != len(request.symbols):
        bad("two symbols map to the same folder name")
    if not TIMEFRAME_RE.fullmatch(request.timeframe):
        bad("timeframe must be a TradingView resolution such as 1D, 240 or 1W", timeframe=request.timeframe)
    if not 5 <= request.ready_timeout_sec <= 600:
        bad("ready_timeout_sec must be between 5 and 600")
    if len(request.required_studies) > 32 or any(not s or len(s) > 128 for s in request.required_studies):
        bad("required_studies must be up to 32 non-empty names")


class Progress:
    """The job.json file that status calls read while a batch runs."""

    def __init__(self, path: Path, *, job_id: str, pid: int, output_dir: Path, total: int) -> None:
        self._path = path
        now = stamp()
        self.state: dict[str, Any] = {
            "schemaVersion": 1,
            "jobId": job_id,
            "pid": pid,
            "state": "running",
            "outputDir": str(output_dir),
            "startedAt": now,
            "updatedAt": now,
            "total": total,
            "done": 0,
            "succeeded": 0,
            "failed": 0,
            "current": None,
            "failures": [],
            "desktopVersionChanged": None,
            "error": None,
        }
        replace_json(self._path, self.state)

    def update(self, **fields: Any) -> None:
        self.state.update(fields)
        self.state["updatedAt"] = stamp()
        replace_json(self._path, self.state)

    def record(self, result: dict[str, Any]) -> None:
        self.state["done"] += 1
        if result["status"] == "ok":
            self.state["succeeded"] += 1
        else:
            self.state["failed"] += 1
            self.state["failures"].append({"symbol": result["symbol"], **result["error"]})
        self.update(current=None)


def previous_desktop_version(output_root: Path, exclude: Path) -> str | None:
    """Desktop version of the newest finished batch from this tool under the output root."""
    best: tuple[float, str | None] | None = None
    for path in [
        *output_root.glob("*/capture-manifest.json"),
        *output_root.glob("*/*/capture-manifest.json"),
    ]:
        if path.parent == exclude:
            continue
        try:
            manifest = read_json(path)
        except (OSError, ValueError):
            continue
        if not isinstance(manifest, dict) or (manifest.get("tool") or {}).get("name") != TOOL_NAME:
            continue
        if manifest.get("state") != "finished" or (manifest.get("totals") or {}).get("succeeded", 0) <= 0:
            continue
        finished = float((manifest.get("finishedAt") or {}).get("unix") or 0)
        if best is None or finished > best[0]:
            best = (finished, (manifest.get("desktop") or {}).get("version"))
    return best[1] if best else None


def run_capture(
    request: CaptureRequest,
    config: Config,
    *,
    job_id: str,
    desktop: DesktopControl,
    pid: int = 0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    validate_request(request)
    out = resolve_inside_root(config.output_root, request.output_dir)
    with BatchLock(config.output_root):
        if request.retry_failed:
            previous, results = _previous_state(out)
            todo = [code for code in request.symbols if results.get(code, {}).get("status") != "ok"]
            if not todo:
                raise CaptureError(
                    NOT_FOUND,
                    "nothing left to retry: every symbol already has a capture",
                    {"output_dir": str(out)},
                )
            ensure_dir(out / "attempts")
            attempt = _next_attempt(out, previous)
            started_at = previous.get("startedAt") or stamp()
        else:
            make_dir_new(out)
            ensure_dir(out / "raw")
            ensure_dir(out / "attempts")
            started_at = stamp()
            write_json_new(
                out / "batch.json",
                {
                    "schemaVersion": 1,
                    "tool": {"name": TOOL_NAME, "version": __version__},
                    "jobId": job_id,
                    "startedAt": started_at,
                    "request": request.to_dict(),
                    "symbolsSha256": sha256_bytes("\n".join(request.symbols).encode("utf-8")),
                },
            )
            results, todo, attempt = {}, list(request.symbols), 1
        attempt_dir = out / "attempts" / str(attempt)
        make_dir_new(attempt_dir)
        progress = Progress(out / "job.json", job_id=job_id, pid=pid, output_dir=out, total=len(todo))
        info: DesktopInfo | None = None
        previous_version: str | None = None
        changed: bool | None = None
        stopped: CaptureError | None = None
        interrupted: BaseException | None = None
        startup: dict[str, Any] | None = None
        try:
            info, driver = desktop.start()
            previous_version = previous_desktop_version(config.output_root, exclude=out)
            changed = previous_version is not None and previous_version != info.version
            progress.update(desktopVersionChanged=changed)
            issues, _ = wait_for_internals(driver, sleep=sleep, clock=clock)
            if issues:
                raise CaptureError(
                    TV_INTERNALS_CHANGED, "TradingView's internals changed", {"failedChecks": issues}
                )
            original = startup = _settle_current_chart(driver, request, sleep=sleep, clock=clock)
            try:
                checked = False  # the self-check runs until one symbol has reached extraction
                for code in todo:
                    progress.update(current=code)
                    try:
                        result = capture_symbol(
                            driver,
                            request,
                            out,
                            code,
                            attempt=attempt,
                            attempt_dir=attempt_dir,
                            self_check=not checked,
                            info=info,
                            sleep=sleep,
                            clock=clock,
                        )
                        checked = True
                    except CaptureError as exc:
                        if not checked and exc.code == TV_INTERNALS_CHANGED:
                            raise
                        result = {
                            "symbol": code,
                            "safeName": safe_name(code),
                            "status": "failed",
                            "attempt": attempt,
                            "error": exc.to_dict(),
                        }
                    results[code] = result
                    progress.record(result)
            finally:
                _restore(driver, original, request)
        except CaptureError as exc:
            stopped = exc
        except Exception as exc:  # a bug must still leave a manifest and a final job state behind
            stopped = CaptureError(INTERNAL_ERROR, f"{type(exc).__name__}: {exc}", {})
        except BaseException as exc:  # SIGTERM/SIGHUP arrive as SystemExit, Ctrl-C as KeyboardInterrupt
            stopped = CaptureError(INTERRUPTED, f"the batch was interrupted ({type(exc).__name__})", {})
            interrupted = exc
        finally:
            desktop.stop()
        symbols = [
            results.get(code) or {"symbol": code, "safeName": safe_name(code), "status": "pending"}
            for code in request.symbols
        ]
        totals = {
            "requested": len(symbols),
            "succeeded": sum(1 for s in symbols if s["status"] == "ok"),
            "failed": sum(1 for s in symbols if s["status"] == "failed"),
            "pending": sum(1 for s in symbols if s["status"] == "pending"),
        }
        state = "stopped" if stopped else "finished"
        error = stopped.to_dict() if stopped else None
        manifest = {
            "schemaVersion": 1,
            "tool": {"name": TOOL_NAME, "version": __version__},
            "jobId": job_id,
            "state": state,
            "error": error,
            "startedAt": started_at,
            "finishedAt": stamp(),
            "attempts": attempt,
            "layout": request.layout,
            "timeframe": request.timeframe,
            "desktop": {
                "version": info.version if info else None,
                "browser": info.browser if info else None,
                "previousVersion": previous_version,
            },
            "desktopVersionChanged": changed,
            "startup": startup,
            "totals": totals,
            "symbols": symbols,
        }
        write_json_new(
            attempt_dir / "attempt.json",
            {
                "attempt": attempt,
                "jobId": job_id,
                "symbols": todo,
                "results": [results[c] for c in todo if c in results],
                "error": error,
            },
        )
        if (out / "capture-manifest.json").exists():
            replace_json(out / "capture-manifest.json", manifest)
        else:
            write_json_new(out / "capture-manifest.json", manifest)
        progress.update(state="failed" if stopped else "finished", current=None, error=error)
        if interrupted is not None:
            raise interrupted
        failures = [
            {"symbol": s["symbol"], "code": s["error"]["code"], "message": s["error"]["message"]}
            for s in symbols
            if s["status"] == "failed"
        ]
        return {
            "jobId": job_id,
            "outputDir": str(out),
            "state": state,
            "totals": totals,
            "failures": failures,
            "desktopVersionChanged": changed,
            "error": error,
        }


def _previous_state(out: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """The last manifest, or, after a crash that left none, what batch.json and the finished folders show."""
    manifest_path = out / "capture-manifest.json"
    if manifest_path.is_file():
        previous = read_json(manifest_path)
        return previous, {s["symbol"]: s for s in previous.get("symbols", [])}
    batch_path = out / "batch.json"
    if not batch_path.is_file():
        raise CaptureError(NOT_FOUND, "no batch at output_dir", {"output_dir": str(out)})
    batch = read_json(batch_path)
    results: dict[str, dict[str, Any]] = {}
    for code in (batch.get("request") or {}).get("symbols", []):
        capture_path = out / "raw" / safe_name(code) / "capture.json"
        if capture_path.is_file():
            results[code] = {
                "symbol": code,
                "safeName": safe_name(code),
                "status": "ok",
                "attempt": read_json(capture_path).get("attempt"),
                "captureSha256": sha256_bytes(capture_path.read_bytes()),
            }
    return {"startedAt": batch.get("startedAt"), "attempts": 0}, results


def _next_attempt(out: Path, previous: dict[str, Any]) -> int:
    """One past every attempt recorded or started, so a killed retry never blocks the next one."""
    started = [int(p.name) for p in (out / "attempts").iterdir() if p.name.isdigit()]
    return max([int(previous.get("attempts") or 0), *started]) + 1


def _settle_current_chart(
    driver: ChartDriver,
    request: CaptureRequest,
    *,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> dict[str, Any]:
    """Wait until the chart TradingView restored at startup has finished loading.

    A switch made while the layout is still loading is undone when the layout's own load completes, and the
    restored symbol can be renamed while it loads (for example to its delayed feed), so this follows whatever
    the chart shows until two reads agree."""
    start = clock()
    previous: ReadySnapshot | None = None
    while True:
        current = ReadySnapshot.from_page(driver.run("ready"))
        verdict = judge(
            target=current.symbol,
            timeframe=current.resolution or request.timeframe,
            current=current,
            previous=previous,
            before_switch=None,
            elapsed=clock() - start,
        )
        if current.symbol and verdict.ready:
            return {
                "symbol": current.symbol,
                "resolution": current.resolution,
                "settled": True,
                "reason": None,
            }
        if clock() - start >= request.ready_timeout_sec:
            # A study that never finishes on the restored symbol must not cost the whole batch; carry on
            # from what the chart shows and let the manifest say so.
            return {
                "symbol": current.symbol,
                "resolution": current.resolution,
                "settled": False,
                "reason": verdict.reason,
            }
        previous = current
        sleep(1.0)


def _restore(driver: ChartDriver, original: Any, request: CaptureRequest) -> None:
    """Put the chart back on the symbol and resolution it showed before the batch."""
    if isinstance(original, dict) and original.get("symbol"):
        with contextlib.suppress(CaptureError):
            driver.run(
                "switch",
                {"symbol": original["symbol"], "timeframe": original.get("resolution") or request.timeframe},
                timeout=40.0,
            )


def capture_symbol(
    driver: ChartDriver,
    request: CaptureRequest,
    out: Path,
    code: str,
    *,
    attempt: int,
    attempt_dir: Path,
    self_check: bool,
    info: DesktopInfo,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> dict[str, Any]:
    started_at = stamp()
    # Send the resolution in the form the chart reports (1D, not D) so an unchanged one is not re-set.
    timeframe = normalize_resolution(request.timeframe)
    before = ReadySnapshot.from_page(driver.run("ready"))
    switched = driver.run("switch", {"symbol": code, "timeframe": timeframe}, timeout=40.0) or {}
    after = switched.get("after") or {}
    if switched.get("timedOut") or not same_symbol(str(after.get("symbol") or ""), code):
        raise CaptureError(SYMBOL_NOT_FOUND, "the chart did not switch to this symbol", {"after": after})
    switched_at = stamp()
    reswitches = 0

    def read() -> ReadySnapshot:
        nonlocal reswitches
        snapshot = ReadySnapshot.from_page(driver.run("ready"))
        if not same_symbol(snapshot.symbol, code) and reswitches < MAX_RESWITCHES:
            # The layout can put its own symbol back right after a switch; ask again.
            reswitches += 1
            driver.run("switch", {"symbol": code, "timeframe": timeframe}, timeout=40.0)
            snapshot = ReadySnapshot.from_page(driver.run("ready"))
        return snapshot

    verdict, snapshot, polls, waited = wait_until_ready(
        read,
        target=code,
        timeframe=timeframe,
        before_switch=before,
        timeout=request.ready_timeout_sec,
        sleep=sleep,
        clock=clock,
    )
    ready_at = stamp()
    extracted = driver.run("extract", timeout=120.0) or {}
    extracted_at = stamp()
    shot = driver.run("screenshot", timeout=60.0) or {}
    screenshot_at = stamp()
    try:
        png = base64.b64decode(str(shot.get("base64") or ""), validate=True)
    except (binascii.Error, ValueError):
        png = b""
    size = png_size(png)
    identity = extracted.get("identity") or {}
    studies = extracted.get("studies") or []
    series = extracted.get("series") or {}
    names = [str(s.get("name") or "") for s in studies]
    missing = [want for want in request.required_studies if not any(want in name for name in names)]
    if self_check:
        failed = [
            name
            for name, ok in (
                ("identity", bool(identity.get("symbol"))),
                ("studies", bool(studies)),
                ("requiredStudies", not missing),
                ("series", bool(series.get("rows"))),
                ("screenshot", size is not None),
            )
            if not ok
        ]
        if failed:
            raise CaptureError(
                TV_INTERNALS_CHANGED,
                f"the self-check failed on {code}",
                {"failedChecks": failed, "missingStudies": missing},
            )
    if not same_symbol(str(identity.get("symbol") or ""), code):
        raise CaptureError(
            SYMBOL_NOT_FOUND, "the extracted chart is not this symbol", {"symbol": identity.get("symbol")}
        )
    if missing:
        raise CaptureError(STUDY_MISSING, "required studies are missing", {"missing": missing})
    if size is None:
        raise CaptureError(CDP_ERROR, "the screenshot is not a PNG", {})
    if not series.get("rows"):
        raise CaptureError(CDP_ERROR, "the chart returned no bars", {})
    name = safe_name(code)
    final = out / "raw" / name
    if final.exists():
        raise CaptureError(OUTPUT_EXISTS, "this symbol already has a capture", {"symbol": code})
    partial = out / "raw" / f".{name}.partial-{attempt}"
    make_dir_new(partial)
    try:
        csv_bytes = str(series.get("csv") or "").encode("utf-8")
        data = {
            "schemaVersion": 1,
            "identity": identity,
            "studies": studies,
            "drawings": extracted.get("drawings") or [],
            "readiness": {
                "polls": polls,
                "waitedSec": round(waited, 3),
                "lastBarTime": snapshot.last_bar_time,
                "unchangedAfterSwitch": list(verdict.unchanged),
                "reswitches": reswitches,
                "studies": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "status": s.status,
                        "lastTime": s.last_time,
                        "digest": s.digest,
                    }
                    for s in snapshot.studies
                ],
            },
        }
        data_bytes = dumps_json(data)
        files = {
            "image.png": {
                "sha256": write_new(partial / "image.png", png),
                "bytes": len(png),
                "width": size[0],
                "height": size[1],
            },
            "chart.csv": {
                "sha256": write_new(partial / "chart.csv", csv_bytes),
                "bytes": len(csv_bytes),
                "rows": series.get("rows"),
                "columns": series.get("columns"),
            },
            "data.json": {"sha256": write_new(partial / "data.json", data_bytes), "bytes": len(data_bytes)},
        }
        finished_at = stamp()
        capture = {
            "schemaVersion": 1,
            "tool": {"name": TOOL_NAME, "version": __version__},
            "desktop": {"version": info.version, "browser": info.browser},
            "captureMethod": CAPTURE_METHOD,
            "pngSource": PNG_SOURCE,
            "csvSource": CSV_SOURCE,
            "symbol": code,
            "resolvedSymbol": identity.get("symbol"),
            "layout": request.layout,
            "timeframe": request.timeframe,
            "attempt": attempt,
            "times": {
                "startedAt": started_at,
                "switchedAt": switched_at,
                "readyAt": ready_at,
                "extractedAt": extracted_at,
                "screenshotAt": screenshot_at,
                "finishedAt": finished_at,
            },
            "files": files,
        }
        capture_sha = write_json_new(partial / "capture.json", capture)
        os.rename(partial, final)
    except BaseException:
        if partial.exists():
            os.rename(partial, attempt_dir / f"{name}.failed")  # keep the evidence; never delete
        raise
    return {
        "symbol": code,
        "safeName": name,
        "status": "ok",
        "attempt": attempt,
        "captureSha256": capture_sha,
        "finishedAt": finished_at,
    }
