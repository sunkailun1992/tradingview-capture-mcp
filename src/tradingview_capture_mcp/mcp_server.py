"""MCP tools on stdio; every tool calls the same functions as the command line."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, diagnostics, jobs, prune, results
from .capture import CaptureRequest
from .config import load_config
from .errors import CaptureError
from .signals import install_server_handlers

INSTRUCTIONS = (
    "Exports TradingView Desktop chart data and screenshots into files and never uploads anything. "
    "The caller chooses the symbols and decides how to check and use the data. capture_start returns "
    "at once with a job id; poll capture_status until the state is finished, failed or crashed, then "
    "read the batch with batch_summary, symbol_data and image_crop. Each captured symbol carries readiness "
    "evidence in its batch_summary entry and in symbol_data's capture block: resolvedSymbol (the code the "
    "chart showed, which can be a delayed feed such as an exchange ending in _DLY), reswitches, "
    "unchangedAfterSwitch (studies whose output still equalled the previous symbol's after the grace period; "
    "check them against the image) and digestMovingAtRead (studies still changing at the read, as in an open "
    "market). TradingView Desktop must not be open when a capture or diagnose starts: the tool launches "
    "it itself with a loopback-only debugging port and quits it at the end. If the user has it open, full "
    "screen or not, capture_start fails at once with TV_ALREADY_RUNNING and creates nothing; ask the user "
    "to quit it with Cmd+Q, never kill it, then call it again (capture_retry continues a batch that "
    "stopped this way mid-run). Errors carry a stable code such as "
    "TV_ALREADY_RUNNING or TV_INTERNALS_CHANGED. "
    "Besides the defaults, symbol_data can return plots (each exported plot with its CSV column and style, "
    "its display bits, forceOverlay when it draws on the main chart although its study sits in another "
    "pane, and lastValid, the last bar that has a value, which the price scale keeps showing after a line "
    "stops), colors (per-bar colours of plots, fills, candles, bars and backgrounds as runs of [first bar "
    "time, last bar time, colour]), fills, bands (horizontal levels) and notExported (what the tool could "
    "not export; a non-empty list is a gap in the data, not proof that nothing is drawn; "
    "unresolvedGraphicColors counts table, label and line colours it could not name, written as null). "
    "A required study hidden on the layout fails with STUDY_HIDDEN; ask the user to show it again. "
    "history_from (YYYY-MM-DD) makes capture_start load each chart's older bars back to 00:00 UTC on that "
    "date before the read, as scrolling left would, without moving the view; chart.csv then holds every "
    "loaded bar. Each symbol's history block (batch_summary entry, symbol_data capture block) gives "
    "firstBarTime, barsCount, reached (the first bar is at or before the date) and endOfData (TradingView's "
    "flag, e.g. limit, when it sent nothing older: the data or the account's history ends there). Without "
    "history_from nothing changes. "
    "Keep only the current day's captures: when the day's captures are done, or before the first capture "
    "of a new day, call output_prune to list the batches from before today, then call it again with "
    "apply=true. It moves those batch folders to the macOS Trash and never deletes anything for good; never "
    "empty the Trash yourself, tell the user the space comes back when they empty it. Files you made from a "
    "capture outside its batch folder follow your own project's rules."
)

app = MCPServer(name="tradingview-capture", version=__version__, instructions=INSTRUCTIONS)


def _coded[F: Callable[..., Any]](fn: F) -> F:
    """Turn CaptureError into a tool error whose text is the JSON error object."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except CaptureError as exc:
            raise ToolError(json.dumps(exc.to_dict(), ensure_ascii=False)) from exc

    return wrapper  # type: ignore[return-value]


@app.tool(
    description="Start capturing TradingView codes from one TradingView Desktop layout into output_dir. "
    "Returns a job id at once. history_from (YYYY-MM-DD, optional) first loads each chart's history back to "
    "00:00 UTC on that date, or as far as TradingView goes."
)
@_coded
def capture_start(
    layout: str,
    symbols: list[str],
    output_dir: str,
    timeframe: str = "1D",
    required_studies: list[str] | None = None,
    ready_timeout_sec: float = 60.0,
    history_from: str | None = None,
) -> dict[str, Any]:
    request = CaptureRequest(
        layout=layout,
        symbols=tuple(symbols),
        timeframe=timeframe,
        output_dir=output_dir,
        required_studies=tuple(required_studies or ()),
        ready_timeout_sec=ready_timeout_sec,
        history_from=history_from,
    )
    return jobs.start(load_config(), request)


@app.tool(
    description="Retry the failed and pending symbols of an existing batch with the batch's own settings, "
    "history_from included. Returns a job id at once."
)
@_coded
def capture_retry(output_dir: str) -> dict[str, Any]:
    return jobs.retry(load_config(), output_dir)


@app.tool(description="Progress of a capture job, by job_id or by output_dir.")
@_coded
def capture_status(job_id: str | None = None, output_dir: str | None = None) -> dict[str, Any]:
    return jobs.status(load_config(), job_id=job_id, output_dir=output_dir)


@app.tool(description="The manifest of a batch: per-symbol status, errors and file hashes.")
@_coded
def batch_summary(output_dir: str) -> dict[str, Any]:
    return results.batch_summary(load_config(), output_dir)


@app.tool(
    description="Structured data for one symbol. parts: identity, tables, labels, lines, boxes, lastValues, "
    "drawings, readiness, inputs, plots, colors, fills, bands, notExported (default identity, tables, "
    "lastValues, drawings). series_last adds the last N CSV rows."
)
@_coded
def symbol_data(
    output_dir: str, symbol: str, parts: list[str] | None = None, series_last: int | None = None
) -> dict[str, Any]:
    return results.symbol_data(load_config(), output_dir, symbol, parts=parts, series_last=series_last)


@app.tool(description="Crop a pixel region of a symbol's image.png and return it as a PNG image.")
@_coded
def image_crop(output_dir: str, symbol: str, x: int, y: int, width: int, height: int) -> Image:
    return Image(data=results.crop(load_config(), output_dir, symbol, x, y, width, height), format="png")


@app.tool(
    description="Start TradingView Desktop briefly and report which internal paths a capture needs are "
    "available. Returns no chart contents."
)
@_coded
def diagnose(layout: str) -> dict[str, Any]:
    return diagnostics.run_doctor(load_config(), layout)


@app.tool(
    description="Keep the current day's capture batches and list the older ones under the output root; "
    "with apply=true move those older batch folders to the macOS Trash. Never deletes anything for good. "
    "keep_days counts today (1 keeps today only)."
)
@_coded
def output_prune(keep_days: int = 1, apply: bool = False) -> dict[str, Any]:
    return prune.prune(load_config(), keep_days=keep_days, apply=apply)


def main() -> None:
    install_server_handlers()
    app.run("stdio")
