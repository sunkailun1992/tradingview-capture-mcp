// A minimal stand-in for the parts of TradingView Desktop's chart model the page scripts read.
export function plotList(rows, firstIndex = 0) {
  return {
    size: () => rows.length,
    firstIndex: () => firstIndex,
    lastIndex: () => firstIndex + rows.length - 1,
    valueAt: (index) => rows[index - firstIndex] || null,
  };
}

// Shaped like TradingView Desktop 3.4.1 (probed 2026-10-14): table cells sit directly under their key, while
// labels, lines and boxes sit one level deeper in a map keyed by false, which stays empty while there are none.
function primitiveCollection(key, items, nested) {
  const collection = new Map();
  const primitives = { _primitivesDataById: new Map(items.map((item) => [item.id, item])) };
  if (nested) collection.set(key, new Map(items.length ? [[false, primitives]] : []));
  else if (items.length) collection.set(key, primitives);
  return collection;
}

export function makeStudy({ id, name, zorder, plots, rows, styles = {}, ohlcPlots, cells = [], labels = [], lines = [], boxes = [], status = 2 }) {
  return {
    id: () => id,
    zorder: () => zorder,
    status: () => ({ type: status }),
    metaInfo: () => ({ description: name, plots, styles, ohlcPlots }),
    data: () => plotList(rows),
    inputs: () => ({ length: 14 }),
    _graphics: {
      _primitivesCollection: {
        dwgtablecells: primitiveCollection('tableCells', cells, false),
        dwglabels: primitiveCollection('labels', labels, true),
        dwglines: primitiveCollection('lines', lines, true),
        dwgboxes: primitiveCollection('boxes', boxes, true),
      },
    },
  };
}

export function makeTradingView({ symbol = 'BINANCE:BTCUSDT.P', resolution = '1D', bars, panes, shapes = [], onSetSymbol }) {
  const state = { symbol, resolution };
  const studies = panes.flat();
  const builtin = { id: () => 'builtin', zorder: () => 10000006, metaInfo: () => ({ description: 'Dividends', plots: [] }) };
  const chart = {
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
  const model = {
    mainSeries: () => ({ bars: () => bars, symbolInfo: () => ({ description: 'Bitcoin / TetherUS', exchange: 'Binance' }) }),
    model: () => ({
      dataSources: () => [...studies].reverse().concat([builtin]),
      panes: () => panes.map((list) => ({ dataSources: () => list })),
    }),
  };
  return {
    TradingViewApi: {
      activeChart: () => chart,
      _activeChartWidgetWV: { value: () => ({ _chartWidget: { model: () => model } }) },
      takeClientScreenshot: async () => ({ width: 2, height: 1, toDataURL: () => 'data:image/png;base64,iVBORw0KGgo=' }),
    },
  };
}
