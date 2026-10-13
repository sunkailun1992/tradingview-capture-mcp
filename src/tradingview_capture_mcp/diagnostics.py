"""Checks of the TradingView internals a capture relies on, and the doctor command."""

from __future__ import annotations

from typing import Any

from .config import Config
from .driver import RealDesktop
from .store import BatchLock
from .validation import check_layout

REQUIRED_CHECKS = (
    "activeChart",
    "takeClientScreenshot",
    "chartWidget",
    "mainSeriesBars",
    "dataSources",
    "panes",
    "studies",
    "shapes",
)
GRAPHICS_COLLECTIONS = 4


def problems(report: dict[str, Any]) -> list[str]:
    """Names of the checks that failed; an empty list means a capture can run."""
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
    if "studies" not in found:
        for study in checks["studies"].get("detail") or []:
            data = study.get("data") or {}
            if not (
                study.get("hasMetaInfo")
                and study.get("zorder") == "function"
                and data.get("valueAt") == "function"
                and len(study.get("collections") or []) >= GRAPHICS_COLLECTIONS
            ):
                found.append("studies.shape")
                break
    return found


def run_doctor(config: Config, layout: str) -> dict[str, Any]:
    check_layout(layout)
    desktop = RealDesktop(config, layout)
    with BatchLock(config.output_root):
        try:
            info, driver = desktop.start()
            report = driver.run("diagnose")
        finally:
            desktop.stop()
    return {
        "desktop": {"version": info.version, "browser": info.browser},
        "problems": problems(report),
        "report": report,
    }
