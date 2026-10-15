"""Builders shared by the Python tests: PNG bytes, config files and finished batches."""

import io
import json
import os
from pathlib import Path

from PIL import Image

from tradingview_capture_mcp.store import ensure_dir, safe_name, write_json_new, write_new

DEFAULT_CSV = "time,open,high,low,close\n1000,1,2,0.5,1.5\n2000,1.5,2.5,1,2"


def png_bytes(width=8, height=6, color=(10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def write_config(tmp_path: Path, output_root: Path, **extra) -> Path:
    lines = [f'output_root = "{output_root}"'] + [
        f"{key} = {json.dumps(value)}" for key, value in extra.items()
    ]
    path = tmp_path / "config.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def make_batch(
    out: Path,
    symbol: str,
    *,
    csv_text: str = DEFAULT_CSV,
    png: bytes | None = None,
    capture_extra: dict | None = None,
) -> Path:
    """A finished one-symbol batch shaped like the capture output; capture_extra adds keys to capture.json."""
    ensure_dir(out)
    ensure_dir(out / "raw")
    folder = out / "raw" / safe_name(symbol)
    ensure_dir(folder)
    data = {
        "schemaVersion": 1,
        "identity": {"symbol": symbol, "resolution": "1D"},
        "studies": [
            {
                "id": "s1",
                "name": "Alpha",
                "pane": 0,
                "visible": True,
                "unresolvedGraphicColors": 0,
                "tables": [{"id": "0", "rows": [["Head", None]]}],
                "labels": [{"text": "9.5", "time": 2000}],
                "lines": [],
                "boxes": [],
                "lastValues": [["Quarter", 11.25]],
                "inputs": {"length": 14},
                "plots": [{"id": "plot_0", "title": "Quarter", "lastValid": {"time": 2000, "value": 11.25}}],
                "colors": [
                    {
                        "id": "plot_1",
                        "kind": "colorer",
                        "target": "plot_0",
                        "runs": [[1000, 2000, "rgba(255,0,0,1)"]],
                    }
                ],
                "fills": [{"id": "fill_0", "between": ["hline_0", "hline_1"]}],
                "bands": [{"id": "hline_0", "value": 90}],
                "notExported": {"plots": [], "graphics": []},
            }
        ],
        "drawings": [],
        "readiness": {"polls": 3},
    }
    write_new(folder / "image.png", png or png_bytes(40, 30))
    write_new(folder / "chart.csv", csv_text.encode("utf-8"))
    write_json_new(folder / "data.json", data)
    write_json_new(
        folder / "capture.json",
        {
            "captureMethod": "CDP_DESKTOP",
            "resolvedSymbol": symbol,
            "readiness": {
                "waitedSec": 10.0,
                "reswitches": 0,
                "unchangedAfterSwitch": ["Alpha"],
                "digestMovingAtRead": [],
            },
            "desktop": {"version": "3.4.1"},
            "times": {"finishedAt": {"iso": "2026-10-14T02:00:00.000+08:00", "unix": 1791914400.0}},
            "files": {},
            **(capture_extra or {}),
        },
    )
    write_json_new(
        out / "capture-manifest.json",
        {
            "tool": {"name": "tradingview-capture-mcp"},
            "state": "finished",
            "symbols": [{"symbol": symbol, "status": "ok"}],
            "totals": {"succeeded": 1},
        },
    )
    return folder
