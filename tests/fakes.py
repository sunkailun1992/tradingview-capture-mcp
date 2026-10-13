"""In-memory stand-ins for TradingView Desktop used by the capture tests."""

import base64

from helpers import png_bytes

from tradingview_capture_mcp.driver import DesktopInfo

OK_DIAGNOSE = {
    "tradingViewApi": "object",
    "checks": [
        {"name": "activeChart", "ok": True, "detail": []},
        {"name": "takeClientScreenshot", "ok": True, "detail": "function"},
        {"name": "chartWidget", "ok": True, "detail": 2},
        {
            "name": "mainSeriesBars",
            "ok": True,
            "detail": {"size": 2, "firstIndex": "function", "lastIndex": "function", "valueAt": "function"},
        },
        {"name": "dataSources", "ok": True, "detail": 4},
        {"name": "panes", "ok": True, "detail": 2},
        {
            "name": "studies",
            "ok": True,
            "detail": [
                {
                    "hasMetaInfo": True,
                    "plots": 2,
                    "zorder": "function",
                    "status": "function",
                    "data": {"size": 2, "valueAt": "function"},
                    "collections": ["dwgtablecells", "dwglabels", "dwglines", "dwgboxes"],
                }
            ],
        },
        {"name": "shapes", "ok": True, "detail": []},
    ],
}
CSV = "time,open,high,low,close,Quarter\n1000,1,2,0.5,1.5,10.5\n2000,1.5,2.5,1,2,11.25"


class FakeChart:
    """Plays the page scripts. After a switch the studies keep the old output for `settle_polls` reads."""

    def __init__(
        self,
        *,
        start_symbol="SSE_DLY:000001",
        settle_polls=2,
        studies=("Alpha", "Beta"),
        unknown=(),
        never_ready=(),
        missing_study=None,
        static_study=None,
        diagnose=None,
    ):
        self.symbol = start_symbol
        self.previous = start_symbol
        self.resolution = "1D"
        self.settle_polls = settle_polls
        self.polls = 10**6
        self.studies = studies
        self.unknown = set(unknown)
        self.never_ready = set(never_ready)
        self.missing_study = missing_study
        self.static_study = static_study
        self.diagnose_report = diagnose or OK_DIAGNOSE
        self.viewport = None
        self.calls = []

    def run(self, script, args=None, *, timeout=60.0):
        self.calls.append((script, dict(args or {})))
        return getattr(self, "_" + script)(args or {})

    def set_viewport(self, viewport):
        self.viewport = viewport

    def clear_viewport(self):
        self.viewport = None

    def _diagnose(self, args):
        return self.diagnose_report

    def _ready(self, args):
        self.polls += 1
        settled = self.polls > self.settle_polls and self.symbol not in self.never_ready
        source = self.symbol if settled else self.previous
        return {
            "symbol": self.symbol,
            "resolution": self.resolution,
            "lastBarTime": 2000,
            "studies": [
                {
                    "id": f"s{i}",
                    "name": name,
                    "status": 2 if settled else 1,
                    "lastTime": 2000,
                    "digest": f"{name}:static" if name == self.static_study else f"{name}:{source}",
                }
                for i, name in enumerate(self.studies)
            ],
        }

    def _switch(self, args):
        before = {"symbol": self.symbol, "resolution": self.resolution}
        if args["symbol"] not in self.unknown:
            self.previous, self.symbol, self.polls = self.symbol, args["symbol"], 0
        self.resolution = args.get("timeframe") or self.resolution
        return {
            "before": before,
            "after": {"symbol": self.symbol, "resolution": self.resolution},
            "timedOut": False,
        }

    def _extract(self, args):
        names = [name for name in self.studies if (self.symbol, name) != self.missing_study]
        return {
            "identity": {"symbol": self.symbol, "resolution": self.resolution, "lastBar": {"time": 2000}},
            "studies": [
                {
                    "id": f"s{i}",
                    "name": name,
                    "tables": [{"id": "0", "rows": [[name, self.symbol]]}],
                    "labels": [],
                    "lines": [],
                    "boxes": [],
                    "lastValues": [["Quarter", 11.25]],
                }
                for i, name in enumerate(names)
            ],
            "drawings": [],
            "series": {"columns": 6, "rows": 2, "csv": CSV},
        }

    def _screenshot(self, args):
        return {"width": 40, "height": 30, "base64": base64.b64encode(png_bytes(40, 30)).decode()}


class FakeDesktop:
    def __init__(self, chart, *, version="3.4.1", fail=None):
        self.chart = chart
        self.version = version
        self.fail = fail
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1
        if self.fail:
            raise self.fail
        return DesktopInfo(version=self.version, browser="Chrome/146.0.7680.216"), self.chart

    def stop(self):
        self.stopped += 1


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
