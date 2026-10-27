// Shared helpers for the page scripts. Nothing here changes chart state.
const TV = window.TradingViewApi;
if (!TV) throw new Error('TV_INTERNALS_CHANGED: window.TradingViewApi is missing');
const chart = TV.activeChart();
const model = TV._activeChartWidgetWV.value()._chartWidget.model();
const bars = model.mainSeries().bars();

// Plot types TradingView's own "Export chart data" leaves out.
const SKIPPED_PLOT_TYPES = new Set(['alertcondition', 'data']);
// The export header names candle plots like this, including the missing ")" after "High";
// the generated CSV mirrors it so headers match native exports column for column.
const OHLC_SUFFIX = { ohlc_open: ' (Open)', ohlc_high: ' (High', ohlc_low: ' (Low)', ohlc_close: ' (Close)' };

function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function text(value) {
  return value === null || value === undefined ? null : String(value);
}

// The listing the shown symbol trades under. Without an exchange's own real-time data the chart shows the feed
// that serves it (BATS:AAPL for NASDAQ:AAPL) and pro_name keeps the listing (TradingView Desktop 3.4.1, 2026-10-27).
function listedSymbol() {
  try {
    const info = model.mainSeries().symbolInfo();
    return info && typeof info.pro_name === 'string' && info.pro_name !== '' ? info.pro_name : null;
  } catch (e) {
    return null;
  }
}

function barTime(index) {
  if (typeof index !== 'number') return null;
  const bar = bars.valueAt(index);
  return bar ? bar[0] : null;
}

// Labels, lines and boxes keep x as a slot in the study's _graphics._indexes, which holds the bar index. A slot
// below -1000000 (TradingView uses -2000000) is a bar outside the loaded range; an index past the last bar is a
// position drawn into the future. Either way there is no bar time.
function graphicsBar(source, x) {
  const indexes = source._graphics && source._graphics._indexes;
  if (!Array.isArray(indexes) || typeof x !== 'number' || x < 0 || x >= indexes.length) return null;
  const index = indexes[x];
  return typeof index === 'number' && index > -1000000 ? index : null;
}

function studyName(source) {
  const meta = source.metaInfo();
  return meta.description || meta.shortDescription || '';
}

function studyStatus(source) {
  try {
    const status = source.status();
    return status && typeof status.type === 'number' ? status.type : null;
  } catch (e) {
    return null;
  }
}

function paneIndexOf(source) {
  const panes = model.model().panes();
  for (let i = 0; i < panes.length; i += 1) {
    if (panes[i].dataSources().indexOf(source) >= 0) return i;
  }
  return -1;
}

// The user's indicators in the order TradingView's export uses: by pane, then by z-order.
function orderedStudies() {
  const ids = new Set(chart.getAllStudies().map((s) => String(s.id)));
  return model.model().dataSources()
    .filter((s) => typeof s.metaInfo === 'function' && typeof s.id === 'function' && ids.has(String(s.id())))
    .map((source) => ({ source, pane: paneIndexOf(source), z: source.zorder() }))
    .sort((a, b) => a.pane - b.pane || a.z - b.z)
    .map((entry) => entry.source);
}

function plotTitle(meta, plot) {
  if (OHLC_SUFFIX[plot.type]) {
    const group = meta.ohlcPlots && meta.ohlcPlots[plot.target];
    return ((group && group.title) || plot.target || plot.id) + OHLC_SUFFIX[plot.type];
  }
  const style = meta.styles && meta.styles[plot.id];
  return (style && style.title) || plot.id;
}

// Plots the native CSV includes, with their position in a data row (position 0 is the time).
function exportedPlots(meta) {
  const out = [];
  meta.plots.forEach((plot, index) => {
    if (SKIPPED_PLOT_TYPES.has(plot.type) || /colorer$/.test(plot.type)) return;
    out.push({ column: index + 1, title: plotTitle(meta, plot) });
  });
  return out;
}

// A study's drawings of one kind in their groups. Table cells sit directly under their key; labels, lines, boxes and
// tables sit one level deeper in a map keyed by force_overlay, true for those a script in another pane draws on the
// main chart (TradingView Desktop 3.4.1, probed 2026-10-14 and 2026-10-27).
function primitiveGroups(source, collection, key) {
  const all = source._graphics && source._graphics._primitivesCollection;
  if (!all || !all[collection] || typeof all[collection].get !== 'function') return [];
  const outer = all[collection].get(key);
  if (!outer) return [];
  if (outer._primitivesDataById) return [{ forceOverlay: false, items: Array.from(outer._primitivesDataById.values()) }];
  if (typeof outer.forEach !== 'function') return [];
  const groups = [];
  outer.forEach((inner, overlay) => {
    const byId = inner && inner._primitivesDataById;
    if (byId) groups.push({ forceOverlay: overlay === true, items: Array.from(byId.values()) });
  });
  return groups;
}

function primitives(source, collection, key) {
  return primitiveGroups(source, collection, key).flatMap((group) => group.items);
}
