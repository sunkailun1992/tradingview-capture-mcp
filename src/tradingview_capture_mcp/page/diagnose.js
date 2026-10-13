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
check('dataSources', () => model.model().dataSources().length);
check('panes', () => model.model().panes().length);
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
      };
    });
});
check('shapes', () => chart.getAllShapes().map((s) => s.name));
return report;
