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
    plots: [{ id: 'plot_0', type: 'line' }, { id: 'plot_1', type: 'colorer' }, { id: 'plot_2', type: 'shapes' }, { id: 'plot_3', type: 'alertcondition' }],
    styles: { plot_0: { title: 'Quarter' }, plot_2: { title: 'Shapes' } },
    rows: [[1000, 10.5, 0, 1, 1], [2000, 11.25, 1, null, 0]],
    cells: [{ id: 1, tid: 0, row: 0, col: 0, t: 'Head' }, { id: 2, tid: 0, row: 1, col: 2, t: 'NaN' }],
    labels: [{ id: 7, x: 1, y: 2.5, t: '9.5', st: 'lup', ci: null, tci: 4278226175, sz: 'small', tt: '' }],
    lines: [{ id: 9, x1: 0, y1: 1, x2: 1, y2: 2, ex: 'n', st: 0, ci: 255, w: 1 }],
  });
  const band = makeStudy({
    id: 'b1', name: 'Band', zorder: -10000, plots: [{ id: 'plot_0', type: 'line' }],
    styles: { plot_0: { title: 'Upper, Inner' } }, rows: [[1000, Number.NaN], [2000, 3]],
  });
  const delta = makeStudy({
    id: 'c1', name: 'Delta', zorder: -10000,
    plots: [{ id: 'plot_0', type: 'ohlc_open', target: 'plotcandle_0' }, { id: 'plot_1', type: 'ohlc_high', target: 'plotcandle_0' }, { id: 'plot_2', type: 'data' }],
    ohlcPlots: { plotcandle_0: { title: 'Body' } }, rows: [[1000, 5, 6, 7], [2000, 8, 9, 10]],
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
  assert.deepEqual(assist.tables, [{ id: '0', rows: [['Head'], [null, null, 'NaN']] }]);
  assert.deepEqual(assist.labels, [{ id: 7, index: 1, time: 2000, price: 2.5, text: '9.5', style: 'lup', color: null, textColor: 4278226175, size: 'small', tooltip: null }]);
  assert.deepEqual(assist.lines, [{ id: 9, index1: 0, time1: 1000, price1: 1, index2: 1, time2: 2000, price2: 2, extend: 'n', style: 0, color: 255, width: 1 }]);
  assert.deepEqual(assist.lastValues, [['Quarter', 11.25], ['Shapes', null]]);
  assert.deepEqual(result.drawings, [{
    id: 's1', type: 'fib_retracement',
    points: [{ index: 0, time: 1000, price: 1 }, { index: 1, time: 2000, price: 2 }],
    levels: [{ coeff: 0, visible: true, text: '', price: 2 }, { coeff: 0.236, visible: false, text: '', price: 1.764 }], reverse: false,
  }]);
  assert.deepEqual(result.identity, {
    symbol: 'BINANCE:BTCUSDT.P', resolution: '1D', description: 'Bitcoin / TetherUS', exchange: 'Binance',
    barsCount: 2, firstBarTime: 1000, lastBar: { time: 2000, open: 1.5, high: 2.5, low: 1, close: 2 },
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
  assert.deepEqual(assist.primitives, { dwgtablecells: 2, dwglabels: 1, dwglines: 1, dwgboxes: 0 });
  assert.deepEqual(report.checks.find((c) => c.name === 'studyCount').detail, { public: 3, matched: 3 });
  assert.deepEqual(report.checks.find((c) => c.name === 'shapes').detail, [{ name: 'fib_retracement', points: 'function' }]);
});

test('common throws a recognisable error when the chart API is missing', async () => {
  await assert.rejects(run('ready', {}, {}), /TV_INTERNALS_CHANGED/);
});
