// Standalone: reports which internal paths a capture relies on, never chart contents.
const report = { tradingViewApi: typeof window.TradingViewApi, checks: [] };

function check(name, fn) {
  try {
    const detail = fn();
    report.checks.push({ name, ok: true, detail: detail === undefined ? null : detail });
  } catch (e) {
    report.checks.push({ name, ok: false, error: String((e && e.message) || e).slice(0, 200) });
  }
}

const TV = window.TradingViewApi;
const PRIMITIVE_KEYS = { dwgtablecells: 'tableCells', dwglabels: 'labels', dwglines: 'lines', dwgboxes: 'boxes' };

// Follows the same path the readers use. null: none of this kind on the chart; a number: how many;
// 'broken': the collection exists but the inner map the readers need is gone.
function primitiveCount(all, collection) {
  if (!all || !all[collection] || typeof all[collection].get !== 'function') return 'broken';
  const outer = all[collection].get(PRIMITIVE_KEYS[collection]);
  if (!outer) return null;
  if (outer._primitivesDataById && typeof outer._primitivesDataById.size === 'number') return outer._primitivesDataById.size;
  if (typeof outer.forEach !== 'function' || typeof outer.size !== 'number') return 'broken';
  // Labels, lines and boxes sit in a map keyed by force_overlay that stays empty while a study draws none of them.
  if (outer.size === 0) return null;
  let count = 0;
  let broken = false;
  outer.forEach((inner) => {
    const byId = inner && inner._primitivesDataById;
    if (byId && typeof byId.size === 'number') count += byId.size;
    else broken = true;
  });
  return broken ? 'broken' : count;
}
let chart = null;
let model = null;
check('activeChart', () => {
  chart = TV.activeChart();
  return ['symbol', 'resolution', 'setSymbol', 'setResolution', 'getAllStudies', 'getAllShapes', 'getShapeById']
    .filter((name) => typeof chart[name] !== 'function');
});
check('takeClientScreenshot', () => typeof TV.takeClientScreenshot);
check('chartWidget', () => {
  model = TV._activeChartWidgetWV.value()._chartWidget.model();
  return Object.keys(model).length;
});
check('mainSeriesBars', () => {
  const b = model.mainSeries().bars();
  return { size: b.size(), firstIndex: typeof b.firstIndex, lastIndex: typeof b.lastIndex, valueAt: typeof b.valueAt };
});
// Loading history from a date (history.js) needs these; a capture without history_from does not.
check('mainSeriesHistory', () => ['requestMoreData', 'requestMoreDataAvailable', 'endOfDataType', 'isLoading']
  .filter((name) => typeof model.mainSeries()[name] !== 'function'));
check('dataSources', () => model.model().dataSources().length);
check('panes', () => model.model().panes().length);
check('studyCount', () => {
  const ids = new Set(chart.getAllStudies().map((s) => String(s.id)));
  const matched = model.model().dataSources().filter((s) => typeof s.id === 'function' && ids.has(String(s.id()))).length;
  return { public: ids.size, matched };
});
check('studies', () => {
  const ids = new Set(chart.getAllStudies().map((s) => String(s.id)));
  return model.model().dataSources()
    .filter((s) => typeof s.id === 'function' && ids.has(String(s.id())))
    .map((s) => {
      const all = s._graphics && s._graphics._primitivesCollection;
      const data = typeof s.data === 'function' ? s.data() : null;
      return {
        hasMetaInfo: typeof s.metaInfo === 'function',
        plots: typeof s.metaInfo === 'function' ? (s.metaInfo().plots || []).length : null,
        zorder: typeof s.zorder,
        status: typeof s.status,
        data: data ? { size: typeof data.size === 'function' ? data.size() : null, valueAt: typeof data.valueAt } : null,
        collections: all
          ? ['dwgtablecells', 'dwglabels', 'dwglines', 'dwgboxes'].filter((k) => all[k] && typeof all[k].get === 'function')
          : [],
        primitives: Object.fromEntries(Object.keys(PRIMITIVE_KEYS).map((c) => [c, primitiveCount(all, c)])),
        // Labels, lines and boxes are placed on bars through this table.
        indexes: Boolean(s._graphics && Array.isArray(s._graphics._indexes)),
        // Property nodes the export reads: plot styles, visibility, palettes, fill styles and bands.
        properties: (() => {
          try {
            const nodes = s.properties().childs() || {};
            return ['styles', 'visible', 'palettes', 'filledAreasStyle', 'bands'].filter((key) => Boolean(nodes[key]));
          } catch (e) {
            return [];
          }
        })(),
      };
    });
});
check('shapes', () => chart.getAllShapes().map((s) => {
  let points = 'missing';
  try {
    points = typeof chart.getShapeById(s.id)._source.points;
  } catch (e) {
    points = 'error';
  }
  return { name: s.name, points };
}));
return report;
