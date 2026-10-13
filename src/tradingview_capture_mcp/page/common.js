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

function barTime(index) {
  if (typeof index !== 'number') return null;
  const bar = bars.valueAt(index);
  return bar ? bar[0] : null;
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

function primitives(source, collection, key) {
  const all = source._graphics && source._graphics._primitivesCollection;
  if (!all || !all[collection] || typeof all[collection].get !== 'function') return [];
  const outer = all[collection].get(key);
  if (!outer) return [];
  const inner = typeof outer.get === 'function' ? outer.get(false) || outer : outer;
  const byId = inner && inner._primitivesDataById;
  return byId ? Array.from(byId.values()) : [];
}
