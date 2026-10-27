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
        {"name": "studyCount", "ok": True, "detail": {"public": 1, "matched": 1}},
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
                    "primitives": {"dwgtablecells": 3, "dwglabels": 0, "dwglines": None, "dwgboxes": None},
                    "indexes": True,
                    "properties": ["styles", "visible", "palettes", "filledAreasStyle", "bands"],
                }
            ],
        },
        {"name": "shapes", "ok": True, "detail": [{"name": "fib_retracement", "points": "function"}]},
        {"name": "mainSeriesHistory", "ok": True, "detail": []},
    ],
}
CSV = "time,open,high,low,close,Quarter\n1000,1,2,0.5,1.5,10.5\n2000,1.5,2.5,1,2,11.25"
# The history script's view of a freshly switched chart: 101 bars, ten seconds apart, from 1000 to 2000.
HISTORY_FIRST, HISTORY_BARS, HISTORY_SPACING = 1000, 101, 10


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
        loading_polls=0,
        ticking=False,
        revert_once=(),
        diagnose_sequence=(),
        resolves=None,
        interrupt_on=None,
        start_alias=None,
        hidden_studies=(),
        history_floor=None,
        history_stuck=(),
        history_breaks_studies=False,
        second_pane=(),
        collapsed_panes=(),
        maximized_pane=None,
        listed=None,
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
        self.diagnose_sequence = list(diagnose_sequence)  # reports returned first, e.g. while the page loads
        self.calls = []
        self.start_symbol = start_symbol
        # The layout is still loading for this many reads after start; a switch made meanwhile is undone.
        self.loading_left = loading_polls
        self.ticking = ticking  # live market: the forming bar changes on every read
        self.revert_once = set(revert_once)  # the first switch to these symbols is undone by the layout
        self.ticks = 0
        self.interrupt_on = interrupt_on  # switching to this symbol raises KeyboardInterrupt (Ctrl-C)
        self.resolves = dict(resolves or {})  # requested code -> the name TradingView serves it under
        # (alias, reads): the restored chart first shows `alias` without bars, then resolves to start_symbol
        self.start_alias = list(start_alias) if start_alias else None
        self.hidden_studies = set(hidden_studies)  # studies whose eye icon is off on the layout
        self.history_floor = history_floor  # TradingView has no bars before this time ("limit")
        self.history_stuck = set(history_stuck)  # symbols whose requests for older bars are never answered
        self.history_breaks_studies = history_breaks_studies  # the studies never finish on the longer history
        self.second_pane = set(second_pane)  # studies in the second pane; the first pane holds the others
        self.collapsed_panes = set(collapsed_panes)  # indexes of the panes collapsed on the layout
        self.maximized_pane = maximized_pane  # index of the pane maximized on the layout, if any
        # shown name -> the listing it trades under (pro_name), e.g. BATS:AAPL -> NASDAQ:AAPL
        self.listed = dict(listed or {})
        self.extracted_settled = []  # whether the studies had finished when each extract ran
        self._new_series()

    def _new_series(self):
        self.history_first, self.history_bars = HISTORY_FIRST, HISTORY_BARS
        self.history_end = None
        self.history_pending = None

    def _listed(self):
        return self.listed.get(self.symbol, self.symbol)

    def run(self, script, args=None, *, timeout=60.0):
        self.calls.append((script, dict(args or {})))
        return getattr(self, "_" + script)(args or {})

    def _diagnose(self, args):
        if self.diagnose_sequence:
            return self.diagnose_sequence.pop(0)
        return self.diagnose_report

    def _ready(self, args):
        if self.start_alias and self.start_alias[1] > 0:
            self.start_alias[1] -= 1
            return {
                "symbol": self.start_alias[0],
                "resolution": self.resolution,
                "lastBarTime": None,
                "studies": [],
            }
        if self.loading_left > 0:
            self.loading_left -= 1
            studies = [
                {"id": f"s{i}", "name": name, "status": 0, "lastTime": 2000, "digest": name}
                for i, name in enumerate(self.studies)
            ]
            return {
                "symbol": self.symbol,
                "resolution": self.resolution,
                "lastBarTime": 2000,
                "studies": studies,
            }
        self.polls += 1
        self.ticks += 1
        settled = self.polls > self.settle_polls and self.symbol not in self.never_ready
        source = self.symbol if settled else self.previous
        return {
            "symbol": self.symbol,
            "listedSymbol": self._listed(),
            "resolution": self.resolution,
            "lastBarTime": 2000,
            "studies": [
                {
                    "id": f"s{i}",
                    "name": name,
                    "status": 2 if settled else 1,
                    "lastTime": 2000,
                    "digest": (f"{name}:static" if name == self.static_study else f"{name}:{source}")
                    + (f":{self.ticks}" if self.ticking and settled else ""),
                }
                for i, name in enumerate(self.studies)
            ],
        }

    def _switch(self, args):
        if args["symbol"] == self.interrupt_on:
            self.interrupt_on = None
            raise KeyboardInterrupt
        before = {"symbol": self.symbol, "resolution": self.resolution}
        if args["symbol"] not in self.unknown:
            self.previous, self.symbol, self.polls = (
                self.symbol,
                self.resolves.get(args["symbol"], args["symbol"]),
                0,
            )
        self.resolution = args.get("timeframe") or self.resolution
        after = {"symbol": self.symbol, "listedSymbol": self._listed(), "resolution": self.resolution}
        self._new_series()
        if self.symbol in self.revert_once:
            self.revert_once.discard(self.symbol)
            self.symbol = self.previous
        if self.loading_left > 0:
            self.symbol = self.start_symbol  # the layout finishes loading and puts its own symbol back
        return {
            "before": before,
            "after": after,
            "timedOut": False,
        }

    def _history(self, args):
        if self.history_pending is not None and self.symbol not in self.history_stuck:
            count = self.history_pending
            oldest = self.history_first - count * HISTORY_SPACING
            if self.history_floor is not None and oldest <= self.history_floor:
                count = (self.history_first - self.history_floor) // HISTORY_SPACING
                oldest, self.history_end = self.history_floor, "limit"
            self.history_first, self.history_bars, self.history_pending = (
                oldest,
                self.history_bars + count,
                None,
            )
            self.polls = 0  # the studies compute again over the longer history
            if self.history_breaks_studies:
                self.never_ready.add(self.symbol)
        loading = self.history_pending is not None
        state = {
            "symbol": self.symbol,
            "listedSymbol": self._listed(),
            "resolution": self.resolution,
            "bars": self.history_bars,
            "firstBarTime": self.history_first,
            "lastBarTime": 2000,
            "loading": loading,
            "canRequest": not loading,
            "endOfData": self.history_end,
            "requested": 0,
        }
        request = args.get("request") or 0
        if request and not loading and self.history_end is None:
            self.history_pending = request
            state["requested"] = request
        return state

    def _extract(self, args):
        names = [name for name in self.studies if (self.symbol, name) != self.missing_study]
        self.extracted_settled.append(self.polls > self.settle_polls)
        return {
            "identity": {
                "symbol": self.symbol,
                "listedSymbol": self._listed(),
                "resolution": self.resolution,
                "barsCount": self.history_bars,
                "firstBarTime": self.history_first,
                "lastBar": {"time": 2000},
            },
            "view": {
                "timezone": "Etc/UTC",
                "chartType": 1,
                "visibleBars": {"from": 1000, "to": 2000},
                "pixelRatio": 2,
                "panes": [
                    {
                        "index": index,
                        "height": 33 if index in self.collapsed_panes else 400,
                        "collapsed": index in self.collapsed_panes,
                        "maximized": self.maximized_pane == index,
                        "priceRange": {"from": 0.5, "to": 2.5},
                        "priceScaleMode": 0,
                    }
                    for index in (0, 1)
                ],
            },
            "studies": [
                {
                    "id": f"s{i}",
                    "name": name,
                    "pane": 1 if name in self.second_pane else 0,
                    "visible": name not in self.hidden_studies,
                    # TradingView keeps the script's encoded body among the inputs as `text`.
                    "inputs": {"length": 14, "text": f"QUJD{name}", "pineId": "PUB;0001"},
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
