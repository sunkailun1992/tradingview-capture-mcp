"""MCP tools on stdio; every tool calls the same functions as the command line."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, diagnostics, jobs, results
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
    "TV_ALREADY_RUNNING or TV_INTERNALS_CHANGED."
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
    "Returns a job id at once."
)
@_coded
def capture_start(
    layout: str,
    symbols: list[str],
    output_dir: str,
    timeframe: str = "1D",
    required_studies: list[str] | None = None,
    ready_timeout_sec: float = 60.0,
) -> dict[str, Any]:
    request = CaptureRequest(
        layout=layout,
        symbols=tuple(symbols),
        timeframe=timeframe,
        output_dir=output_dir,
        required_studies=tuple(required_studies or ()),
        ready_timeout_sec=ready_timeout_sec,
    )
    return jobs.start(load_config(), request)


@app.tool(description="Retry the failed and pending symbols of an existing batch. Returns a job id at once.")
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
    "drawings, readiness, inputs (default identity, tables, lastValues, drawings). "
    "series_last adds the last N CSV rows."
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


def main() -> None:
    install_server_handlers()
    app.run("stdio")
