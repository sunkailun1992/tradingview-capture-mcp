import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { makeTradingView, plotList } from './fake_tv.mjs';

const PAGE = new URL('../../src/tradingview_capture_mcp/page/', import.meta.url);
const source = (name) => readFileSync(new URL(`${name}.js`, PAGE), 'utf8');

async function extract(window) {
  const code = ['(async () => {', 'const ARGS = {};', source('common'), source('extract'), '})()'].join('\n');
  return JSON.parse(JSON.stringify(await vm.runInNewContext(code, { window, setTimeout })));
}

function fib(reverse) {
  return makeTradingView({
    bars: plotList([[1000, 1, 2, 0.5, 1.5], [2000, 1.5, 2.5, 1, 2]]),
    panes: [[]],
    shapes: [{ id: 'f', name: 'fib_retracement', points: [{ index: 0, price: 100 }, { index: 1, price: 200 }],
      properties: { level1: [0, '#000', true, ''], level2: [0.382, '#000', true, ''], level3: [1, '#000', true, ''], reverse } }],
  });
}

test('fib retracement levels are measured from the second point', async () => {
  const [drawing] = (await extract(fib(false))).drawings;
  assert.deepEqual(drawing.levels.map((l) => l.price), [200, 161.8, 100]);
});

test('reversed fib retracements are measured from the first point', async () => {
  const [drawing] = (await extract(fib(true))).drawings;
  assert.deepEqual(drawing.levels.map((l) => l.price), [100, 138.2, 200]);
});
