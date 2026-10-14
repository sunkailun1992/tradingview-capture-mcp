"""Command line: capture, status, read, crop, prune, doctor, and the stdio MCP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from . import diagnostics, jobs, prune, results
from .capture import CaptureRequest, run_capture
from .config import load_config
from .driver import RealDesktop
from .errors import INVALID_ARGUMENT, CaptureError
from .signals import exit_on_termination


def _box(value: str) -> tuple[int, int, int, int]:
    parts = value.split(",")
    if len(parts) != 4 or not all(p.strip().isdigit() for p in parts):
        raise CaptureError(INVALID_ARGUMENT, "box must be x,y,width,height in pixels", {"box": value})
    x, y, width, height = (int(p) for p in parts)
    return x, y, width, height


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingview-capture", description="Capture TradingView Desktop charts for AI agents."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="start a batch (in the background unless --foreground)")
    cap.add_argument("--output-dir", required=True)
    cap.add_argument("--layout")
    cap.add_argument("--symbol", action="append", default=[], help="a TradingView code; repeat for more")
    cap.add_argument("--symbols-file", help="a file with one TradingView code per line")
    cap.add_argument("--timeframe", default="1D")
    cap.add_argument("--required-study", action="append", default=[])
    cap.add_argument("--ready-timeout", type=float, default=60.0)
    cap.add_argument("--retry-failed", action="store_true", help="retry the failed symbols of --output-dir")
    cap.add_argument("--foreground", action="store_true")
    job = sub.add_parser("run-job", help=argparse.SUPPRESS)
    job.add_argument("--job-id", required=True)
    status = sub.add_parser("status", help="progress of a job, or a batch summary")
    which = status.add_mutually_exclusive_group(required=True)
    which.add_argument("--job-id")
    which.add_argument("--output-dir")
    status.add_argument(
        "--summary", action="store_true", help="print the batch manifest (needs --output-dir)"
    )
    read = sub.add_parser("read", help="structured data for one symbol")
    read.add_argument("--output-dir", required=True)
    read.add_argument("--symbol", required=True)
    read.add_argument("--part", action="append")
    read.add_argument("--series-last", type=int)
    crop = sub.add_parser("crop", help="save a crop of a symbol's image")
    crop.add_argument("--output-dir", required=True)
    crop.add_argument("--symbol", required=True)
    crop.add_argument("--box", required=True, help="x,y,width,height")
    crop.add_argument("--out", required=True)
    clean = sub.add_parser(
        "prune", help="list batches from before today; with --apply move them to the Trash (never deletes)"
    )
    clean.add_argument("--keep-days", type=int, default=1, help="days to keep, today included (default 1)")
    clean.add_argument("--apply", action="store_true", help="move the listed batches to the Trash")
    doctor = sub.add_parser("doctor", help="check the TradingView Desktop internals a capture needs")
    doctor.add_argument("--layout", required=True)
    sub.add_parser("mcp", help="run the MCP server on stdio")
    return parser


def _capture(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    config = load_config()
    if args.retry_failed:
        request = jobs.retry_request(config, args.output_dir)
    else:
        symbols = list(args.symbol)
        if args.symbols_file:
            lines = Path(args.symbols_file).read_text(encoding="utf-8").splitlines()
            symbols += [line.strip() for line in lines if line.strip()]
        request = CaptureRequest(
            layout=args.layout or "",
            symbols=tuple(symbols),
            timeframe=args.timeframe,
            output_dir=args.output_dir,
            required_studies=tuple(args.required_study),
            ready_timeout_sec=args.ready_timeout,
        )
    if not args.foreground:
        return jobs.start(config, request), 0
    summary = run_capture(
        request, config, job_id=uuid.uuid4().hex, desktop=RealDesktop(config, request.layout), pid=os.getpid()
    )
    return summary, 0 if summary["state"] == "finished" else 1


def _dispatch(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    if args.command == "capture":
        return _capture(args)
    config = load_config()
    if args.command == "run-job":
        summary = jobs.run_job(config, args.job_id)
        return summary, 0 if summary["state"] == "finished" else 1
    if args.command == "status":
        if args.summary:
            if not args.output_dir:
                raise CaptureError(INVALID_ARGUMENT, "--summary needs --output-dir", {})
            return results.batch_summary(config, args.output_dir), 0
        return jobs.status(config, job_id=args.job_id, output_dir=args.output_dir), 0
    if args.command == "read":
        return results.symbol_data(
            config, args.output_dir, args.symbol, parts=args.part, series_last=args.series_last
        ), 0
    if args.command == "crop":
        return results.save_crop(config, args.output_dir, args.symbol, _box(args.box), args.out), 0
    if args.command == "prune":
        report = prune.prune(config, keep_days=args.keep_days, apply=args.apply)
        return report, 1 if report["totals"]["failed"] else 0
    if args.command == "doctor":
        report = diagnostics.run_doctor(config, args.layout)
        return report, 0 if not report["problems"] else 1
    raise CaptureError(INVALID_ARGUMENT, f"unknown command {args.command}", {})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "mcp":
        from .mcp_server import main as serve

        serve()
        return 0
    try:
        with exit_on_termination():
            payload, code = _dispatch(args)
    except CaptureError as exc:
        payload, code = {"error": exc.to_dict()}, 2
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
