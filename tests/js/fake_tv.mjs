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

export function makeStudy({ id, name, zorder, plots, rows, styles = {}, ohlcPlots, cells = [], labels = [], lines = [], boxes = [], status = 2, indexes = [], plotProps = {}, meta = {}, props = {}, tables = [], graphics = {} }) {
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
        dwgtables: primitiveCollection('tables', tables, false),
        dwglabels: primitiveCollection('labels', labels, true),
        dwglines: primitiveCollection('lines', lines, true),
        dwgboxes: primitiveCollection('boxes', boxes, true),
        // Every live study has this one; it holds script statistics, not drawings.
        performance: new Map([['performance', {}]]),
        // Kinds the export does not read (polylines, linefills, ...) are empty maps on the live chart.
        dwgpolylines: new Map(),
        ...graphics,
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
    mainSeries: () => ({ bars: () => bars, symbolInfo: () => ({ description: 'Bitcoin / TetherUS', exchange: 'Binance', pricescale: 100, minmov: 1 }) }),
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
