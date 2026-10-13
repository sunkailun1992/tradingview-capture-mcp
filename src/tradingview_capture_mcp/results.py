"""Read batches: summaries, per-symbol data, CSV rows and crops."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from .config import Config
from .errors import INVALID_ARGUMENT, NOT_FOUND, CaptureError
from .images import crop_png
from .store import read_json, resolve_inside_root, safe_name, write_new

DEFAULT_PARTS = ("identity", "tables", "lastValues", "drawings")
STUDY_PARTS = ("tables", "labels", "lines", "boxes", "lastValues", "inputs")
ALL_PARTS = ("identity", "drawings", "readiness", *STUDY_PARTS)
MAX_SERIES_ROWS = 1000


def batch_summary(config: Config, output_dir: str) -> dict[str, Any]:
    out = resolve_inside_root(config.output_root, output_dir)
    if (out / "capture-manifest.json").is_file():
        return read_json(out / "capture-manifest.json")
    if (out / "job.json").is_file():
        return {"state": "running", "job": read_json(out / "job.json")}
    raise CaptureError(NOT_FOUND, "no batch at output_dir", {"output_dir": str(out)})


def _symbol_dir(config: Config, output_dir: str, symbol: str) -> Path:
    folder = resolve_inside_root(config.output_root, output_dir) / "raw" / safe_name(symbol)
    if not (folder / "capture.json").is_file():
        raise CaptureError(NOT_FOUND, "this symbol has no capture in the batch", {"symbol": symbol})
    return folder


def symbol_data(
    config: Config,
    output_dir: str,
    symbol: str,
    parts: list[str] | None = None,
    series_last: int | None = None,
) -> dict[str, Any]:
    wanted = tuple(parts) if parts else DEFAULT_PARTS
    unknown = [p for p in wanted if p not in ALL_PARTS]
    if unknown:
        raise CaptureError(
            INVALID_ARGUMENT, "unknown parts", {"unknown": unknown, "allowed": list(ALL_PARTS)}
        )
    if series_last is not None and not 1 <= series_last <= MAX_SERIES_ROWS:
        raise CaptureError(INVALID_ARGUMENT, f"series_last must be between 1 and {MAX_SERIES_ROWS}", {})
    folder = _symbol_dir(config, output_dir, symbol)
    data = read_json(folder / "data.json")
    capture = read_json(folder / "capture.json")
    result: dict[str, Any] = {
        "symbol": symbol,
        "capture": {
            "capturedAt": (capture.get("times") or {}).get("finishedAt"),
            "captureMethod": capture.get("captureMethod"),
            "desktopVersion": (capture.get("desktop") or {}).get("version"),
            "files": capture.get("files"),
        },
    }
    for part in ("identity", "drawings", "readiness"):
        if part in wanted:
            result[part] = data.get(part)
    study_parts = [p for p in STUDY_PARTS if p in wanted]
    if study_parts:
        result["studies"] = [
            {"name": s.get("name"), "id": s.get("id"), **{p: s.get(p) for p in study_parts}}
            for s in data.get("studies", [])
        ]
    if series_last:
        rows = list(csv.reader(io.StringIO((folder / "chart.csv").read_text(encoding="utf-8"))))
        result["series"] = {"columns": rows[0] if rows else [], "rows": rows[1:][-series_last:]}
    return result


def crop(config: Config, output_dir: str, symbol: str, x: int, y: int, width: int, height: int) -> bytes:
    return crop_png(_symbol_dir(config, output_dir, symbol) / "image.png", x, y, width, height)


def save_crop(
    config: Config, output_dir: str, symbol: str, box: tuple[int, int, int, int], destination: str
) -> dict[str, Any]:
    data = crop(config, output_dir, symbol, *box)
    target = resolve_inside_root(config.output_root, destination)
    return {"path": str(target), "sha256": write_new(target, data), "bytes": len(data)}
