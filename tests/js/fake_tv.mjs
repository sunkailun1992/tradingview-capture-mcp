// A minimal stand-in for the parts of TradingView Desktop's chart model the page scripts read.
export function plotList(rows, firstIndex = 0) {
  return {
    size: () => rows.length,
    firstIndex: () => firstIndex,
    lastIndex: () => firstIndex + rows.length - 1,
    valueAt: (index) => rows[index - firstIndex] || null,
  };
}

// Shaped like TradingView Desktop 3.4.1 (probed 2026-10-14 and 2026-10-27): table cells sit directly under their key,
// while labels, lines, boxes and tables sit one level deeper in a map keyed by force_overlay (false, or true for
// drawings a script in another pane puts on the main chart), which stays empty while there are none.
function primitiveCollection(key, items, nested, overlay = []) {
  const collection = new Map();
  const primitives = (list) => ({ _primitivesDataById: new Map(list.map((item) => [item.id, item])) });
  if (nested) {
    const groups = [];
    if (items.length) groups.push([false, primitives(items)]);
    if (overlay.length) groups.push([true, primitives(overlay)]);
    collection.set(key, new Map(groups));
  } else if (items.length) collection.set(key, primitives(items));
  return collection;
}

// Labels, lines and boxes store x as a slot in _graphics._indexes, which holds the bar index; -2000000 marks a bar
// outside the loaded range (probed on TradingView Desktop 3.4.1, 2026-10-14).
// Study properties as TradingView Desktop 3.4.1 holds them (probed 2026-10-14): live plot styles (colour, plot type,
// location, display) sit in properties().childs().styles.childs()[plotId]; palettes, filledAreasStyle and bands are
// whole nodes read with state(); flags such as visible are read with value().
function studyProperties(plotProps, props) {
  const node = (value) => ({ value: () => value });
  const styles = Object.fromEntries(Object.entries(plotProps).map(([plotId, fields]) => [plotId, {
    childs: () => Object.fromEntries(Object.entries(fields).map(([key, value]) => [key, node(value)])),
  }]));
  const childs = { styles: { childs: () => styles } };
  for (const [key, value] of Object.entries(props)) {
    childs[key] = typeof value === 'boolean' ? node(value) : { state: () => value };
  }
  return { childs: () => childs };
}

export function makeStudy({ id, name, zorder, plots, rows, styles = {}, ohlcPlots, cells = [], labels = [], lines = [], boxes = [], status = 2, indexes = [], plotProps = {}, meta = {}, props = {}, tables = [], graphics = {}, overlay = {} }) {
  return {
    id: () => id,
    zorder: () => zorder,
    status: () => ({ type: status }),
    metaInfo: () => ({ description: name, plots, styles, ohlcPlots, ...meta }),
    data: () => plotList(rows),
    inputs: () => ({ length: 14 }),
    properties: () => studyProperties(plotProps, { visible: true, showLabelsOnPriceScale: true, ...props }),
    _graphics: {
      _indexes: indexes,
      _primitivesCollection: {
        dwgtablecells: primitiveCollection('tableCells', cells, false),
        dwgtables: primitiveCollection('tables', tables, true, overlay.tables),
        dwglabels: primitiveCollection('labels', labels, true, overlay.labels),
        dwglines: primitiveCollection('lines', lines, true, overlay.lines),
        dwgboxes: primitiveCollection('boxes', boxes, true, overlay.boxes),
        // Every live study has this one; it holds script statistics, not drawings.
        performance: new Map([['performance', {}]]),
        // Kinds the export does not read (polylines, linefills, ...) are empty maps on the live chart.
        dwgpolylines: new Map(),
        ...graphics,
      },
    },
  };
}

// The main series' history methods as TradingView Desktop 3.4.1 has them (probed 2026-10-15): requestMoreData(n) asks the
// server for n older bars, marks the series loading and holds further requests until the answer; endOfDataType() is the
// data_completed flag of the last answer ('limit' once the server sends nothing older), null before that.
// `history: null` builds a series without these methods.
function makeHistory(history) {
  if (history === null) return {};
  const state = { loading: false, available: true, end: null, refuse: false, requests: [], ...history };
  return {
    isLoading: () => state.loading,
    requestMoreDataAvailable: () => state.available,
    endOfDataType: () => state.end,
    requestMoreData: (count) => {
      if (state.refuse || !state.available) return; // the live series returns quietly while it is not ready
      state.requests.push(count);
      state.loading = true;
      state.available = false;
    },
  };
}

// The picture as TradingView Desktop 3.4.1 describes it (probed 2026-10-27): getPanes() lists the panes top to bottom
// with their height in CSS pixels and whether they are collapsed or maximized, each with the visible price range and
// mode of its main price scale; the time scale's strict range gives the first and last bar index on screen, empty
// slots right of the last bar included. `view: null` builds a chart without any of these.
function makeView(view, paneCount) {
  if (view === null) return { chart: {}, window: {}, timeScale: undefined };
  const spec = {
    timezone: 'Asia/Tokyo', chartType: 1, strictRange: { first: -3, last: 5 }, pixelRatio: 2,
    panes: Array.from({ length: paneCount }, (_, i) => ({
      height: i === 0 ? 400 : 120, collapsed: false, maximized: false, priceRange: { from: 0.5, to: 2.5 }, mode: 0,
    })),
    ...view,
  };
  const paneApi = (pane, index) => {
    const scale = { getVisiblePriceRange: () => pane.priceRange, getMode: () => pane.mode };
    return {
      paneIndex: () => index, getHeight: () => pane.height, isCollapsed: () => pane.collapsed,
      isMaximized: () => pane.maximized, getMainSourcePriceScale: () => scale,
    };
  };
  return {
    chart: {
      getPanes: () => spec.panes.map(paneApi),
      getTimezone: () => spec.timezone,
      chartType: () => spec.chartType,
    },
    window: { devicePixelRatio: spec.pixelRatio },
    timeScale: () => ({
      visibleBarsStrictRange: () => ({ firstBar: () => spec.strictRange.first, lastBar: () => spec.strictRange.last }),
    }),
  };
}

// `listed` maps a shown name to the listing it trades under (symbolInfo().pro_name), e.g. BATS:AAPL -> NASDAQ:AAPL on
// accounts without the exchange's own real-time data (probed on TradingView Desktop 3.4.1, 2026-10-27).
export function makeTradingView({ symbol = 'BINANCE:BTCUSDT.P', resolution = '1D', bars, panes, shapes = [], onSetSymbol, history = {}, view = {}, listed = {} }) {
  const state = { symbol, resolution };
  const studies = panes.flat();
  const builtin = { id: () => 'builtin', zorder: () => 10000006, metaInfo: () => ({ description: 'Dividends', plots: [] }) };
  const picture = makeView(view, panes.length);
  const chart = {
    ...picture.chart,
    symbol: () => state.symbol,
    resolution: () => state.resolution,
    setSymbol: (value, done) => {
      state.symbol = value;
      if (onSetSymbol) onSetSymbol(value, done);
      else done();
    },
    setResolution: (value, done) => {
      state.resolution = value;
      done();
    },
    getAllStudies: () => studies.map((s) => ({ id: s.id(), name: s.metaInfo().description })),
    getAllShapes: () => shapes.map((s) => ({ id: s.id, name: s.name })),
    getShapeById: (id) => {
      const shape = shapes.find((s) => s.id === id);
      return { _source: { points: () => shape.points }, getProperties: () => shape.properties };
    },
  };
  const series = {
    bars: () => bars,
    symbolInfo: () => ({
      description: 'Bitcoin / TetherUS', exchange: 'Binance', pricescale: 100, minmov: 1,
      type: 'crypto', currency_code: 'USDT', timezone: 'Etc/UTC', session: '24x7',
      pro_name: listed[state.symbol] || state.symbol,
    }),
    ...makeHistory(history),
  };
  const model = {
    mainSeries: () => series,
    model: () => ({
      dataSources: () => [...studies].reverse().concat([builtin]),
      panes: () => panes.map((list) => ({ dataSources: () => list })),
      timeScale: picture.timeScale,
    }),
  };
  return {
    ...picture.window,
    TradingViewApi: {
      activeChart: () => chart,
      _activeChartWidgetWV: { value: () => ({ _chartWidget: { model: () => model } }) },
      takeClientScreenshot: async () => ({ width: 2, height: 1, toDataURL: () => 'data:image/png;base64,iVBORw0KGgo=' }),
    },
  };
}
