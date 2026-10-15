"""Checks of the TradingView internals a capture relies on, and the doctor command."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .config import Config
from .driver import ChartDriver, RealDesktop
from .store import BatchLock
from .validation import check_layout

REQUIRED_CHECKS = (
    "activeChart",
    "takeClientScreenshot",
    "chartWidget",
    "mainSeriesBars",
    "dataSources",
    "panes",
    "studyCount",
    "studies",
    "shapes",
)
# Needed only to load history from a date (history_from).
HISTORY_CHECK = "mainSeriesHistory"
GRAPHICS_COLLECTIONS = 4
INTERNALS_TIMEOUT = 30.0


def problems(report: dict[str, Any], *, history: bool = False) -> list[str]:
    """Names of the checks that failed; an empty list means a capture can run.

    The history methods count only for a capture that loads history, so a TradingView change that removes them
    does not stop the captures that never use them."""
    checks = {c.get("name"): c for c in report.get("checks", []) if isinstance(c, dict)}
    found = [name for name in REQUIRED_CHECKS if not (checks.get(name) or {}).get("ok")]
    if "activeChart" not in found and checks["activeChart"].get("detail"):
        found.append("activeChart.methods")
    if "takeClientScreenshot" not in found and checks["takeClientScreenshot"].get("detail") != "function":
        found.append("takeClientScreenshot.function")
    if "mainSeriesBars" not in found:
        bars = checks["mainSeriesBars"].get("detail") or {}
        if not all(bars.get(key) == "function" for key in ("firstIndex", "lastIndex", "valueAt")):
            found.append("mainSeriesBars.methods")
    if "studyCount" not in found:
        counts = checks["studyCount"].get("detail") or {}
        if counts.get("matched", 0) < counts.get("public", 0):
            found.append("studies.unmatched")
    if "studies" not in found:
        studies = checks["studies"].get("detail") or []
        for study in studies:
            data = study.get("data") or {}
            if not (
                study.get("hasMetaInfo")
                and study.get("zorder") == "function"
                and data.get("valueAt") == "function"
                and len(study.get("collections") or []) >= GRAPHICS_COLLECTIONS
            ):
                found.append("studies.shape")
                break
        if any("broken" in (study.get("primitives") or {}).values() for study in studies):
            found.append("studies.primitives")
        # Without the index table labels, lines and boxes cannot be placed on their bars.
        if any(study.get("indexes") is not True for study in studies):
            found.append("studies.indexes")
        # Plot styles and the visibility flag exist on every study; without them nothing says what is shown.
        if any(not {"styles", "visible"} <= set(study.get("properties") or []) for study in studies):
            found.append("studies.properties")
    if "shapes" not in found:
        shapes = checks["shapes"].get("detail") or []
        if any(not isinstance(shape, dict) or shape.get("points") != "function" for shape in shapes):
            found.append("shapes.points")
    if history:
        if not (checks.get(HISTORY_CHECK) or {}).get("ok"):
            found.append(HISTORY_CHECK)
        elif checks[HISTORY_CHECK].get("detail"):
            found.append(f"{HISTORY_CHECK}.methods")
    return found


def wait_for_internals(
    driver: ChartDriver,
    *,
    timeout: float = INTERNALS_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    history: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    """Poll the diagnose script until every check passes or the timeout ends.

    Right after start the chart API answers before its internal model is built, so a single early
    check would report a change that is only a page still loading."""
    start = clock()
    while True:
        report = driver.run("diagnose")
        found = problems(report, history=history)
        if not found or clock() - start >= timeout:
            return found, report
        sleep(1.0)


def run_doctor(config: Config, layout: str) -> dict[str, Any]:
    check_layout(layout)
    desktop = RealDesktop(config, layout)
    with BatchLock(config.output_root):
        try:
            info, driver = desktop.start()
            # The doctor reports everything a capture may need, history loading included.
            found, report = wait_for_internals(driver, history=True)
        finally:
            desktop.stop()
    return {
        "desktop": {"version": info.version, "browser": info.browser},
        "problems": found,
        "report": report,
    }
