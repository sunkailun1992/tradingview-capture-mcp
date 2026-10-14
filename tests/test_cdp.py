import json
import threading
from http.server import BaseHTTPRequestHandler

import pytest
from loopback_http import LoopbackHTTPServer
from websockets.sync.server import serve

from tradingview_capture_mcp import cdp
from tradingview_capture_mcp.errors import CaptureError


@pytest.fixture
def devtools():
    """A fake DevTools page endpoint; tests register replies per method."""
    replies = {}

    def handler(connection):
        for raw in connection:
            message = json.loads(raw)
            connection.send(json.dumps({"method": "Runtime.consoleAPICalled", "params": {}}))
            reply = replies.get(message["method"], {"error": {"code": -32601, "message": "unknown method"}})
            if callable(reply):
                reply = reply(message.get("params", {}))
            if reply is None:
                continue
            connection.send(json.dumps({"id": message["id"], **reply}))

    server = serve(handler, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.socket.getsockname()[1]
    yield f"ws://127.0.0.1:{port}/devtools/page/TEST", replies
    server.shutdown()
    thread.join(timeout=5)


def test_call_skips_events_and_returns_the_result(devtools):
    url, replies = devtools
    replies["Browser.getVersion"] = {"result": {"product": "Chrome/146"}}
    with cdp.CdpSession(url) as session:
        assert session.call("Browser.getVersion") == {"product": "Chrome/146"}


def test_evaluate_returns_the_value(devtools):
    url, replies = devtools
    replies["Runtime.evaluate"] = lambda params: {
        "result": {"result": {"type": "object", "value": {"byValue": params["returnByValue"]}}}
    }
    with cdp.CdpSession(url) as session:
        assert session.evaluate("1") == {"byValue": True}


def test_evaluate_carries_large_values(devtools):
    url, replies = devtools
    big = "x" * (5 * 1024 * 1024)
    replies["Runtime.evaluate"] = {"result": {"result": {"type": "string", "value": big}}}
    with cdp.CdpSession(url) as session:
        assert len(session.evaluate("big")) == len(big)


def test_page_exceptions_become_cdp_errors(devtools):
    url, replies = devtools
    replies["Runtime.evaluate"] = {
        "result": {
            "result": {},
            "exceptionDetails": {
                "text": "Uncaught",
                "exception": {"description": "TypeError: x is undefined\n    at <anonymous>:1:1"},
            },
        }
    }
    with cdp.CdpSession(url) as session, pytest.raises(CaptureError) as err:
        session.evaluate("x.y")
    assert (err.value.code, err.value.message) == ("CDP_ERROR", "TypeError: x is undefined")


def test_the_internals_marker_has_its_own_code(devtools):
    url, replies = devtools
    replies["Runtime.evaluate"] = {
        "result": {
            "result": {},
            "exceptionDetails": {
                "text": "Uncaught",
                "exception": {"description": "Error: TV_INTERNALS_CHANGED: window.TradingViewApi is missing"},
            },
        }
    }
    with cdp.CdpSession(url) as session, pytest.raises(CaptureError) as err:
        session.evaluate("x")
    assert err.value.code == "TV_INTERNALS_CHANGED"


def test_protocol_errors_and_timeouts(devtools):
    url, replies = devtools
    replies["Never.answers"] = lambda params: None
    with cdp.CdpSession(url) as session:
        with pytest.raises(CaptureError) as err:
            session.call("No.such")
        assert err.value.message == "unknown method"
        with pytest.raises(CaptureError) as err:
            session.call("Never.answers", timeout=0.3)
        assert "timed out" in err.value.message


def test_a_refused_connection_is_a_cdp_error():
    with pytest.raises(CaptureError) as err:
        cdp.CdpSession("ws://127.0.0.1:9/devtools/page/none", open_timeout=1)
    assert err.value.code == "CDP_ERROR"


def test_select_chart_page():
    targets = [
        {"type": "page", "url": "https://www.tradingview.com/chart/AbCd1234/"},
        {"type": "page", "url": "https://www.tradingview.com/chart/Other999/"},
        {"type": "worker", "url": "https://www.tradingview.com/chart/AbCd1234/"},
    ]
    assert cdp.select_chart_page(targets, "AbCd1234") is targets[0]
    with pytest.raises(CaptureError) as err:
        cdp.select_chart_page(targets, "Missing1")
    assert err.value.code == "LAYOUT_NOT_FOUND"
    with pytest.raises(CaptureError) as err:
        cdp.select_chart_page([*targets, dict(targets[0])], "AbCd1234")
    assert err.value.code == "LAYOUT_NOT_UNIQUE"


def test_http_json_reads_loopback():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps({"path": self.path}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert cdp.http_json(server.server_address[1], "/json/version") == {"path": "/json/version"}
    finally:
        server.shutdown()
        server.server_close()
