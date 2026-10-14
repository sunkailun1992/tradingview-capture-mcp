import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { makeStudy, makeTradingView, plotList } from './fake_tv.mjs';

const PAGE = new URL('../../src/tradingview_capture_mcp/page/', import.meta.url);
const STANDALONE = new Set(['alive', 'diagnose']);
const source = (name) => readFileSync(new URL(`${name}.js`, PAGE), 'utf8');

// Mirrors tradingview_capture_mcp.page.build(): the expression Runtime.evaluate receives.
async function run(name, args, window, globals = {}) {
  const parts = ['(async () => {', `const ARGS = ${JSON.stringify(args || {})};`];
  if (!STANDALONE.has(name)) parts.push(source('common'));
  parts.push(source(name), '})()');
  const value = await vm.runInNewContext(parts.join('\n'), { window, setTimeout, clearTimeout, ...globals });
  return JSON.parse(JSON.stringify(value)); // returnByValue hands back plain JSON
}

function fixture(overrides = {}) {
  const assist = makeStudy({
    id: 'a1', name: 'Assist', zorder: -20000,
    plots: [{ id: 'plot_0', type: 'line' }, { id: 'plot_1', type: 'colorer', target: 'plot_0' }, { id: 'plot_2', type: 'shapes' }, { id: 'plot_3', type: 'alertcondition' }],
    styles: { plot_0: { title: 'Quarter' }, plot_2: { title: 'Shapes', text: 'TD', size: 'tiny', isHidden: false } },
    plotProps: { plot_2: { color: '#2962ff', plottype: 'shape_triangle_down', location: 'AboveBar', display: 15 } },
    // An RGB script: colours are ARGB numbers with the alpha in the top byte (0xFFFF0000 is opaque red). The live
    // chart keeps the ids of force_overlay plots in a Set.
    meta: { isRGB: true, _forceOverlayPlotIds: new Set(['plot_2']) },
    rows: [[1000, 10.5, 0xFFFF0000, 1, 1], [2000, 11.25, 0xFFFF0000, null, 0]],
    tables: [{ id: 0, pos: 'top_right', rows: 2, cols: 3 }],
    cells: [
      { id: 1, tid: 0, row: 0, col: 0, t: 'Head', tc: 0xFFFFFFFF, bgc: 0 },
      { id: 2, tid: 0, row: 1, col: 2, t: 'NaN', tc: 0xFF000000, bgc: 0x80FF0000 },
    ],
    // x is a slot in indexes: slot 0 is a bar before the loaded range, slots 1 and 2 are bars 0 and 1.
    indexes: [-2000000, 0, 1],
    labels: [
      { id: 7, x: 2, y: 2.5, yl: 'ab', t: '9.5', st: 'lup', ci: null, tci: 4278226175, sz: 'small', ta: 'center', tt: '' },
      { id: 8, x: 0, y: 1.5, yl: 'pr', t: '7', st: 'ldn', ci: null, tci: null, sz: 'small', ta: 'center', tt: '' },
    ],
    lines: [{ id: 9, x1: 1, y1: 1, x2: 2, y2: 2, ex: 'n', st: 0, ci: 255, w: 1 }],
  });
  const band = makeStudy({
    id: 'b1', name: 'Band', zorder: -10000, plots: [{ id: 'plot_0', type: 'line' }],
    styles: { plot_0: { title: 'Upper, Inner' } }, rows: [[1000, Number.NaN], [2000, 3]], props: { visible: false },
  });
  const delta = makeStudy({
    id: 'c1', name: 'Delta', zorder: -10000,
    plots: [{ id: 'plot_0', type: 'ohlc_open', target: 'plotcandle_0' }, { id: 'plot_1', type: 'ohlc_high', target: 'plotcandle_0' }, { id: 'plot_2', type: 'data' }],
    ohlcPlots: { plotcandle_0: { title: 'Body', forceOverlay: true } }, rows: [[1000, 5, 6, 7], [2000, 8, 9, 10]],
    // Candles drawn on the main chart from another pane, with values shown in volume format (83.42K).
    meta: { isRGB: true, _forceOverlayPlotIds: new Set(['plotcandle_0', 'plot_0', 'plot_1']), format: { type: 'volume' } },
    // A kind of drawing the export does not read yet: it must be reported, never dropped silently.
    graphics: { dwgpolylines: new Map([['polylines', new Map([[false, { _primitivesDataById: new Map([[1, { id: 1 }]]) }]])]]) },
  });
  return makeTradingView({
    bars: plotList([[1000, 1, 2, 0.5, 1.5], [2000, 1.5, 2.5, 1, 2]]),
    panes: [[assist, band], [delta]],
    shapes: [{
      id: 's1', name: 'fib_retracement', points: [{ index: 0, price: 1 }, { index: 1, price: 2 }],
      properties: { level1: [0, '#808080', true, ''], level2: [0.236, '#F23645', false, ''], reverse: false },
    }],
    ...overrides,
  });
}

test('extract describes every exported plot with its CSV column and style', async () => {
  const result = await run('extract', {}, fixture());
  const [assist, band, delta] = result.studies;
  assert.deepEqual(assist.plots, [
    { id: 'plot_0', title: 'Quarter', type: 'line', csvColumn: 5, plotType: null, location: null, color: null, text: null, size: null, hidden: false, display: null, forceOverlay: false, lastValid: { time: 2000, value: 11.25 } },
    { id: 'plot_2', title: 'Shapes', type: 'shapes', csvColumn: 6, plotType: 'shape_triangle_down', location: 'AboveBar', color: '#2962ff', text: 'TD', size: 'tiny', hidden: false, display: 15, forceOverlay: true, lastValid: { time: 1000, value: 1 } },
  ]);
  // The last bar has no value here, so the last valid one is a bar earlier.
  assert.deepEqual(band.plots[0].lastValid, { time: 2000, value: 3 });
  assert.deepEqual(band.plots.map((p) => [p.title, p.csvColumn]), [['Upper, Inner', 7]]);
  assert.deepEqual(delta.plots.map((p) => [p.title, p.csvColumn, p.forceOverlay]), [['Body (Open)', 8, true], ['Body (High', 9, true]]);
  assert.deepEqual([assist.format, delta.format], [null, { type: 'volume' }]);
  const header = result.series.csv.split('\n')[0].split(',');
  assert.equal(header[6], 'Shapes');
});

test('extract turns the per-bar colours of an RGB script into runs', async () => {
  const result = await run('extract', {}, fixture());
  const [assist, band] = result.studies;
  assert.deepEqual(assist.colors, [{ id: 'plot_1', kind: 'colorer', target: 'plot_0', runs: [[1000, 2000, 'rgba(255,0,0,1)']], unresolved: 0 }]);
  assert.deepEqual(band.colors, []);
});

test('extract resolves palette colours and exports fills and bands', async () => {
  const osc = makeStudy({
    id: 'o1', name: 'Osc', zorder: -10000,
    plots: [{ id: 'plot_0', type: 'line' }, { id: 'plot_1', type: 'colorer', target: 'fill_0', palette: 'palette_0' }, { id: 'plot_2', type: 'bg_colorer', palette: 'palette_0' }],
    styles: { plot_0: { title: 'Wave' } },
    rows: [[1000, 50, 5, 113], [2000, 60, 7, Number.NaN]],
    // A script without RGB colours stores a value that the palette's table turns into one of its colour slots.
    meta: {
      palettes: { palette_0: { colors: { 0: { name: 'Color 0' }, 1: { name: 'Color 1' } }, valToIndex: { 5: 0, 113: 1 } } },
      filledAreas: [{ id: 'fill_0', objAId: 'hline_0', objBId: 'hline_1', type: 'hline_hline', title: 'Zone', palette: 'palette_0' }],
      bands: [{ id: 'hline_0', name: 'Upper' }, { id: 'hline_1', name: 'Level' }],
    },
    props: {
      palettes: { palette_0: { colors: { 0: { color: 'rgba(62,191,255,0.41)', style: 0, width: 1 }, 1: { color: 'rgba(0,0,0,0)', style: 0, width: 1 } } } },
      filledAreasStyle: { fill_0: { color: '#2962ff', transparency: 0, visible: true } },
      bands: [
        { color: '#DBDBDB', linestyle: 2, linewidth: 1, value: 90, visible: true },
        { color: 'rgba(54,58,69,0.01)', linestyle: 2, linewidth: 1, value: 70, visible: false },
      ],
    },
  });
  const [study] = (await run('extract', {}, fixture({ panes: [[osc]], shapes: [] }))).studies;
  assert.deepEqual(study.fills, [{ id: 'fill_0', title: 'Zone', type: 'hline_hline', between: ['hline_0', 'hline_1'], visible: true, fillType: null, color: '#2962ff', transparency: 0 }]);
  assert.deepEqual(study.bands, [
    { id: 'hline_0', name: 'Upper', value: 90, color: '#DBDBDB', visible: true, lineStyle: 2, lineWidth: 1 },
    { id: 'hline_1', name: 'Level', value: 70, color: 'rgba(54,58,69,0.01)', visible: false, lineStyle: 2, lineWidth: 1 },
  ]);
  // 7 is not in the palette's table: the colour is unknown, and the export counts it instead of guessing.
  assert.deepEqual(study.colors, [
    { id: 'plot_1', kind: 'colorer', target: 'fill_0', runs: [[1000, 1000, 'rgba(62,191,255,0.41)'], [2000, 2000, null]], unresolved: 1 },
    { id: 'plot_2', kind: 'bg_colorer', target: null, runs: [[1000, 1000, 'rgba(0,0,0,0)'], [2000, 2000, null]], unresolved: 0 },
  ]);
});

test('extract says whether each study is shown and what it could not export', async () => {
  const [assist, band, delta] = (await run('extract', {}, fixture())).studies;
  assert.deepEqual([assist.visible, assist.showLabelsOnPriceScale, band.visible], [true, true, false]);
  assert.deepEqual(assist.notExported, { plots: [], graphics: [] });
  assert.deepEqual(delta.notExported, { plots: [{ id: 'plot_2', type: 'data', target: null }], graphics: ['dwgpolylines'] });
});

test('a drawing kind that cannot be read is reported, never taken for empty', async () => {
  const odd = makeStudy({
    id: 'q1', name: 'Odd', zorder: -10000, plots: [], rows: [[1000], [2000]],
    graphics: {
      dwglinefills: { 7: { id: 7 } }, // a plain object instead of a Map
      dwgpolylines: { values: () => { throw new Error('changed'); } },
    },
  });
  const [study] = (await run('extract', {}, fixture({ panes: [[odd]], shapes: [] }))).studies;
  assert.deepEqual(study.notExported.graphics.sort(), ['dwglinefills', 'dwgpolylines']);
});

test('tables, labels and lines of a palette script take their colours from the shared palette', async () => {
  const osc = makeStudy({
    id: 'p1', name: 'Panel', zorder: -10000, plots: [], rows: [[1000], [2000]],
    meta: { palettes: { palette_common: { colors: { 0: { name: 'Color 0' }, 1: { name: 'Color 1' } } } } },
    props: { palettes: { palette_common: { colors: { 0: { color: '#DBDBDB' }, 1: { color: 'rgba(255,152,0,0.2)' } } } } },
    tables: [{ id: 1, pos: 'top_right' }],
    // 9 is not a slot of the palette: unknown, which must not read as "no colour".
    cells: [{ id: 1, tid: 1, row: 0, col: 0, t: 'Head', tc: 0, bgc: 1 }, { id: 2, tid: 1, row: 0, col: 1, t: 'x', tc: 0, bgc: 9 }],
    indexes: [0, 1],
    labels: [{ id: 3, x: 1, y: 5, t: 'L', st: 'n', ci: 'rgba(1,2,3,1)', tci: 1, sz: 'small', tt: '' }],
  });
  const [study] = (await run('extract', {}, fixture({ panes: [[osc]], shapes: [] }))).studies;
  assert.deepEqual(study.tables[0].cellColors, [[{ text: '#DBDBDB', background: 'rgba(255,152,0,0.2)' }, { text: '#DBDBDB', background: null }]]);
  assert.deepEqual([study.labels[0].colorCss, study.labels[0].textColorCss], ['rgba(1,2,3,1)', 'rgba(255,152,0,0.2)']);
  assert.equal(study.unresolvedGraphicColors, 1);
});

test('extract gives boxes the bar times of their edges', async () => {
  const zone = makeStudy({
    id: 'z1', name: 'Zones', zorder: -10000, plots: [], rows: [[1000], [2000]], indexes: [-2000000, 0, 1],
    boxes: [{ id: 5, x1: 1, y1: 2, x2: 2, y2: 1, bc: 255 }],
  });
  const result = await run('extract', {}, fixture({ panes: [[zone]], shapes: [] }));
  assert.deepEqual(result.studies[0].boxes, [{ id: 5, x1: 1, y1: 2, x2: 2, y2: 1, bc: 255, index1: 0, time1: 1000, index2: 1, time2: 2000 }]);
});

test('extract orders studies by pane then z-order and writes export-shaped CSV', async () => {
  const result = await run('extract', {}, fixture());
  assert.deepEqual(result.studies.map((s) => s.name), ['Assist', 'Band', 'Delta']);
  assert.equal(result.series.csv, [
    'time,open,high,low,close,Quarter,Shapes,"Upper, Inner",Body (Open),Body (High',
    '1000,1,2,0.5,1.5,10.5,1,,5,6',
    '2000,1.5,2.5,1,2,11.25,,3,8,9',
  ].join('\n'));
  assert.equal(result.series.rows, 2);
  assert.equal(result.series.columns, 10);
});

test('extract returns tables, labels, lines, last values, drawings and identity', async () => {
  const result = await run('extract', {}, fixture());
  const [assist] = result.studies;
  assert.deepEqual(assist.tables, [{
    id: '0', position: 'top_right', rows: [['Head'], [null, null, 'NaN']],
    cellColors: [
      [{ text: 'rgba(255,255,255,1)', background: 'rgba(0,0,0,0)' }],
      [null, null, { text: 'rgba(0,0,0,1)', background: 'rgba(255,0,0,0.5)' }],
    ],
  }]);
  // Bar times come through the graphics index table; a label on a bar outside the loaded range has none.
  assert.deepEqual(assist.labels, [
    { id: 7, index: 1, time: 2000, price: 2.5, text: '9.5', style: 'lup', color: null, textColor: 4278226175, size: 'small', tooltip: null, yloc: 'ab', textAlign: 'center', colorCss: null, textColorCss: 'rgba(0,140,255,1)' },
    { id: 8, index: null, time: null, price: 1.5, text: '7', style: 'ldn', color: null, textColor: null, size: 'small', tooltip: null, yloc: 'pr', textAlign: 'center', colorCss: null, textColorCss: null },
  ]);
  assert.deepEqual(assist.lines, [{ id: 9, index1: 0, time1: 1000, price1: 1, index2: 1, time2: 2000, price2: 2, extend: 'n', style: 0, color: 255, width: 1, colorCss: 'rgba(0,0,255,0)' }]);
  assert.deepEqual(assist.lastValues, [['Quarter', 11.25], ['Shapes', null]]);
  assert.deepEqual(result.drawings, [{
    id: 's1', type: 'fib_retracement',
    points: [{ index: 0, time: 1000, price: 1 }, { index: 1, time: 2000, price: 2 }],
    levels: [{ coeff: 0, visible: true, text: '', price: 2 }, { coeff: 0.236, visible: false, text: '', price: 1.764 }], reverse: false,
  }]);
  assert.deepEqual(result.identity, {
    symbol: 'BINANCE:BTCUSDT.P', resolution: '1D', description: 'Bitcoin / TetherUS', exchange: 'Binance',
    barsCount: 2, firstBarTime: 1000, lastBar: { time: 2000, open: 1.5, high: 2.5, low: 1, close: 2 },
    priceScale: 100, minMove: 1,
  });
});

test('ready reports status, last time and a digest per study', async () => {
  const result = await run('ready', {}, fixture());
  assert.equal(result.symbol, 'BINANCE:BTCUSDT.P');
  assert.equal(result.lastBarTime, 2000);
  assert.deepEqual(result.studies.map((s) => [s.id, s.name, s.status, s.lastTime]), [['a1', 'Assist', 2, 2000], ['b1', 'Band', 2, 2000], ['c1', 'Delta', 2, 2000]]);
  assert.equal(typeof result.studies[0].digest, 'string');
});

test('switch changes resolution and symbol and reports a stuck callback', async () => {
  const moved = await run('switch', { symbol: 'BINANCE:ETHUSDT.P', timeframe: '1D' }, fixture({ resolution: '240' }));
  assert.deepEqual(moved, {
    before: { symbol: 'BINANCE:BTCUSDT.P', resolution: '240' },
    after: { symbol: 'BINANCE:ETHUSDT.P', resolution: '1D' },
    timedOut: false,
  });
  const stuck = await run('switch', { symbol: 'BINANCE:ETHUSDT.P', timeframe: '1D', waitMs: 20 }, fixture({ onSetSymbol: () => {} }));
  assert.equal(stuck.timedOut, true);
});

test('switch clears its timeout once the chart answers', async () => {
  const pending = new Set();
  const globals = {
    setTimeout: () => { const id = Symbol('timer'); pending.add(id); return id; },
    clearTimeout: (id) => pending.delete(id),
  };
  await run('switch', { symbol: 'BINANCE:ETHUSDT.P', timeframe: '1D' }, fixture({ resolution: '240' }), globals);
  assert.equal(pending.size, 0);
});

test('screenshot returns the PNG payload without the data URL prefix', async () => {
  assert.deepEqual(await run('screenshot', {}, fixture()), { width: 2, height: 1, base64: 'iVBORw0KGgo=' });
});

test('alive and diagnose never throw', async () => {
  assert.deepEqual(await run('alive', {}, {}), { api: 'undefined', symbol: null });
  const broken = await run('diagnose', {}, {});
  assert.equal(broken.tradingViewApi, 'undefined');
  assert.ok(broken.checks.every((c) => c.ok === false));
  const report = await run('diagnose', {}, fixture());
  assert.ok(report.checks.every((c) => c.ok), JSON.stringify(report.checks));
  const studies = report.checks.find((c) => c.name === 'studies').detail;
  assert.equal(studies.length, 3);
  assert.deepEqual(studies[0].collections, ['dwgtablecells', 'dwglabels', 'dwglines', 'dwgboxes']);
  const assist = studies.find((s) => s.plots === 4); // diagnose lists studies in the chart's internal order
  // No boxes: the live chart then holds an empty map where the boxes would be, which means none, not broken.
  assert.deepEqual(assist.primitives, { dwgtablecells: 2, dwglabels: 2, dwglines: 1, dwgboxes: null });
  assert.equal(assist.indexes, true);
  assert.deepEqual(assist.properties, ['styles', 'visible']);
  assert.deepEqual(report.checks.find((c) => c.name === 'studyCount').detail, { public: 3, matched: 3 });
  assert.deepEqual(report.checks.find((c) => c.name === 'shapes').detail, [{ name: 'fib_retracement', points: 'function' }]);
});

test('diagnose calls primitives broken when they sit where the readers do not look', async () => {
  const odd = makeStudy({ id: 'o1', name: 'Odd', zorder: -10000, plots: [], rows: [[1000], [2000]] });
  const elsewhere = new Map([[true, { _primitivesDataById: new Map([[1, { id: 1 }]]) }]]);
  odd._graphics._primitivesCollection.dwglabels = new Map([['labels', elsewhere]]);
  const report = await run('diagnose', {}, fixture({ panes: [[odd]], shapes: [] }));
  const [study] = report.checks.find((c) => c.name === 'studies').detail;
  assert.deepEqual(study.primitives, { dwgtablecells: null, dwglabels: 'broken', dwglines: null, dwgboxes: null });
});

test('common throws a recognisable error when the chart API is missing', async () => {
  await assert.rejects(run('ready', {}, {}), /TV_INTERNALS_CHANGED/);
});
