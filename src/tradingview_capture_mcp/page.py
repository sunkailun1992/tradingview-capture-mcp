"""Load the fixed page scripts and wrap them for Runtime.evaluate."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

SCRIPTS = ("alive", "ready", "switch", "extract", "screenshot", "diagnose")
_STANDALONE = {"alive", "diagnose"}


@cache
def _source(name: str) -> str:
    return (
        resources.files("tradingview_capture_mcp").joinpath("page", f"{name}.js").read_text(encoding="utf-8")
    )


def build(name: str, args: dict[str, Any] | None = None) -> str:
    """The expression for one page script; arguments travel as a JSON literal, never as code."""
    if name not in SCRIPTS:
        raise ValueError(f"unknown page script: {name}")
    parts = ["(async () => {", f"const ARGS = {json.dumps(args or {}, ensure_ascii=False)};"]
    if name not in _STANDALONE:
        parts.append(_source("common"))
    parts.append(_source(name))
    parts.append("})()")
    return "\n".join(parts)
