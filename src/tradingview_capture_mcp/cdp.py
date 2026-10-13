"""A small synchronous Chrome DevTools Protocol client for one page."""

from __future__ import annotations

import contextlib
import json
import time
import urllib.request
from typing import Any

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .errors import CDP_ERROR, LAYOUT_NOT_FOUND, LAYOUT_NOT_UNIQUE, TV_INTERNALS_CHANGED, CaptureError

# DevTools only listens on loopback; never send these requests through a system proxy.
_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(port: int, path: str, *, timeout: float = 3.0) -> Any:
    with _LOCAL_OPENER.open(f"http://127.0.0.1:{port}{path}", timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def select_chart_page(targets: list[dict[str, Any]], layout: str) -> dict[str, Any]:
    needle = f"/chart/{layout}/"
    pages = [t for t in targets if t.get("type") == "page" and needle in str(t.get("url", ""))]
    if not pages:
        raise CaptureError(LAYOUT_NOT_FOUND, "no TradingView tab shows this layout", {"layout": layout})
    if len(pages) > 1:
        raise CaptureError(
            LAYOUT_NOT_UNIQUE, "more than one tab shows this layout", {"layout": layout, "tabs": len(pages)}
        )
    return pages[0]


class CdpSession:
    """One WebSocket connection to a page target; calls run one at a time."""

    def __init__(self, ws_url: str, *, open_timeout: float = 10.0) -> None:
        self._stack = contextlib.ExitStack()
        try:
            # No proxy, no compression, no size limit: screenshots arrive as multi-megabyte strings.
            self._ws = self._stack.enter_context(
                connect(
                    ws_url,
                    proxy=None,
                    compression=None,
                    max_size=None,
                    open_timeout=open_timeout,
                    ping_interval=None,
                )
            )
        except (OSError, WebSocketException) as exc:
            raise CaptureError(CDP_ERROR, f"cannot connect to the page: {exc}", {}) from exc
        self._next_id = 0

    def call(
        self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 60.0
    ) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        deadline = time.monotonic() + timeout
        try:
            self._ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                reply = json.loads(self._ws.recv(timeout=remaining))
                if reply.get("id") != message_id:
                    continue  # an event, or the late reply to an earlier call that timed out
                if "error" in reply:
                    raise CaptureError(
                        CDP_ERROR, str(reply["error"].get("message", "DevTools error")), {"method": method}
                    )
                return reply.get("result") or {}
        except TimeoutError as exc:
            raise CaptureError(
                CDP_ERROR, f"{method} timed out after {timeout:g}s", {"method": method}
            ) from exc
        except WebSocketException as exc:
            raise CaptureError(
                CDP_ERROR, f"the DevTools connection failed: {exc}", {"method": method}
            ) from exc

    def evaluate(self, expression: str, *, timeout: float = 60.0) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "timeout": int(timeout * 1000),
            },
            timeout=timeout + 5.0,
        )
        details = result.get("exceptionDetails")
        if details:
            text = (
                (details.get("exception") or {}).get("description")
                or details.get("text")
                or "page script failed"
            )
            first_line = str(text).splitlines()[0][:300]
            code = TV_INTERNALS_CHANGED if "TV_INTERNALS_CHANGED" in first_line else CDP_ERROR
            raise CaptureError(code, first_line, {"source": "page"})
        return (result.get("result") or {}).get("value")

    def close(self) -> None:
        self._stack.close()

    def __enter__(self) -> CdpSession:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
