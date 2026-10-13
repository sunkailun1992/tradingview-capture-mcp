"""Compare two TradingView-style CSV exports row by row, keyed by the time column.

Used to check generated CSVs against TradingView's own export. Prints a JSON report and exits 1
when the headers differ or any compared row differs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[0], {row[0]: row for row in rows[1:] if row}


def compare(a: Path, b: Path, skip_last: int = 1) -> dict[str, Any]:
    header_a, rows_a = load(a)
    header_b, rows_b = load(b)
    shared = sorted(set(rows_a) & set(rows_b), key=float)
    checked = shared[:-skip_last] if skip_last else shared
    width = min(len(header_a), len(header_b))
    mismatches: dict[str, dict[str, Any]] = {}
    for time in checked:
        row_a, row_b = rows_a[time], rows_b[time]
        for i in range(width):
            value_a = row_a[i] if i < len(row_a) else ""
            value_b = row_b[i] if i < len(row_b) else ""
            if value_a != value_b:
                entry = mismatches.setdefault(
                    f"{i + 1}:{header_a[i]}",
                    {"count": 0, "first": {"time": time, "a": value_a, "b": value_b}},
                )
                entry["count"] += 1
    return {
        "headerEqual": header_a == header_b,
        "columns": [len(header_a), len(header_b)],
        "headerDiff": [
            [i + 1, x, y] for i, (x, y) in enumerate(zip(header_a, header_b, strict=False)) if x != y
        ],
        "rows": [len(rows_a), len(rows_b)],
        "overlap": len(shared),
        "checked": len(checked),
        "mismatchedColumns": mismatches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two TradingView-style CSV exports by time.")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument(
        "--skip-last", type=int, default=1, help="ignore the newest N shared rows (the forming bar)"
    )
    args = parser.parse_args(argv)
    report = compare(args.a, args.b, args.skip_last)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["headerEqual"] and not report["mismatchedColumns"] else 1


if __name__ == "__main__":
    sys.exit(main())
