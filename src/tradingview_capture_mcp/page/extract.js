// Reads everything a capture keeps, in one call so the parts describe the same moment.
const lastIndex = bars.lastIndex();
const last = bars.valueAt(lastIndex);
let info = null;
try {
  info = model.mainSeries().symbolInfo();
} catch (e) {
  info = null;
}
const identity = {
  symbol: chart.symbol(),
  resolution: chart.resolution(),
  description: (info && info.description) || null,
  exchange: (info && (info.exchange || info.listed_exchange)) || null,
  barsCount: bars.size(),
  firstBarTime: barTime(bars.firstIndex()),
  lastBar: last ? { time: last[0], open: num(last[1]), high: num(last[2]), low: num(last[3]), close: num(last[4]) } : null,
  // Prices are shown in steps of minMove / priceScale (priceScale 100 means two decimals).
  priceScale: info && typeof info.pricescale === 'number' ? info.pricescale : null,
  minMove: info && typeof info.minmov === 'number' ? info.minmov : null,
};

function plain(value) {
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (e) {
    return null;
  }
}

// Live plot properties (colour, plot type, location); missing ones stay null rather than stopping the read.
function plotStyles(source) {
  try {
    const styles = source.properties().childs().styles.childs();
    const out = {};
    for (const [plotId, node] of Object.entries(styles)) {
      const fields = node && typeof node.childs === 'function' ? node.childs() : {};
      out[plotId] = {};
      for (const key of ['color', 'plottype', 'location']) {
        const child = fields[key];
        if (child && typeof child.value === 'function') out[plotId][key] = plain(child.value());
      }
    }
    return out;
  } catch (e) {
    return {};
  }
}

const ordered = orderedStudies();
// chart.csv column of each study's first exported plot: after time and OHLC, studies in export order.
const csvOffsets = [];
ordered.reduce((offset, source) => {
  csvOffsets.push(offset);
  return offset + exportedPlots(source.metaInfo()).length;
}, 5);
const studies = ordered.map((source, studyIndex) => {
  const meta = source.metaInfo();
  const tables = new Map();
  for (const cell of primitives(source, 'dwgtablecells', 'tableCells')) {
    const id = String(cell.tid || 0);
    if (!tables.has(id)) tables.set(id, []);
    const rows = tables.get(id);
    while (rows.length <= cell.row) rows.push([]);
    const row = rows[cell.row];
    while (row.length <= cell.col) row.push(null);
    row[cell.col] = text(cell.t);
  }
  const at = (x) => graphicsBar(source, x);
  const labels = primitives(source, 'dwglabels', 'labels').map((l) => ({
    id: l.id, index: at(l.x), time: barTime(at(l.x)), price: num(l.y), text: text(l.t) || '',
    style: l.st || null, color: l.ci === undefined ? null : l.ci, textColor: l.tci === undefined ? null : l.tci,
    size: l.sz || null, tooltip: l.tt || null,
  }));
  const lines = primitives(source, 'dwglines', 'lines').map((l) => ({
    id: l.id, index1: at(l.x1), time1: barTime(at(l.x1)), price1: num(l.y1),
    index2: at(l.x2), time2: barTime(at(l.x2)), price2: num(l.y2),
    extend: l.ex || null, style: l.st === undefined ? null : l.st, color: l.ci === undefined ? null : l.ci,
    width: l.w === undefined ? null : l.w,
  }));
  // Boxes keep every field TradingView stores; their left and right edges also get bar times, as lines do.
  const boxes = primitives(source, 'dwgboxes', 'boxes').map((b) => ({
    ...(plain(b) || { id: b.id }), index1: at(b.x1), time1: barTime(at(b.x1)), index2: at(b.x2), time2: barTime(at(b.x2)),
  }));
  const data = source.data();
  const row = data && data.size() > 0 ? data.valueAt(lastIndex) : null;
  const lastValues = exportedPlots(meta).map((p) => [p.title, row ? num(row[p.column]) : null]);
  let inputs = null;
  try {
    inputs = source.inputs ? plain(source.inputs()) : null;
  } catch (e) {
    inputs = null;
  }
  const liveStyles = plotStyles(source);
  const plots = exportedPlots(meta).map((p, i) => {
    const plot = meta.plots[p.column - 1];
    const style = (meta.styles || {})[plot.id] || {};
    const live = liveStyles[plot.id] || {};
    return {
      id: plot.id, title: p.title, type: plot.type, csvColumn: csvOffsets[studyIndex] + i,
      plotType: live.plottype === undefined ? null : live.plottype,
      location: live.location === undefined ? null : live.location,
      color: live.color === undefined ? null : live.color,
      text: typeof style.text === 'string' && style.text !== '' ? style.text : null,
      size: style.size || null, hidden: style.isHidden === true,
    };
  });
  return {
    id: String(source.id()), name: studyName(source), pane: paneIndexOf(source), status: studyStatus(source), inputs,
    tables: Array.from(tables, ([id, rows]) => ({ id, rows })), labels, lines, boxes, lastValues, plots,
  };
});

// Fib retracement levels are measured from the second point back toward the first (checked against
// TradingView's own labels on a live chart); `reverse` swaps the two points.
const drawings = chart.getAllShapes().map((shape) => {
  const api = chart.getShapeById(shape.id);
  let points = [];
  try {
    points = api._source.points().map((p) => ({ index: p.index, time: barTime(p.index), price: num(p.price) }));
  } catch (e) {
    points = [];
  }
  let props = {};
  try {
    props = api.getProperties() || {};
  } catch (e) {
    props = {};
  }
  const reverse = props.reverse === true;
  const [first, second] = points;
  const span = shape.name === 'fib_retracement' && first && second && first.price !== null && second.price !== null
    ? (reverse ? { from: first.price, to: second.price } : { from: second.price, to: first.price })
    : null;
  const levels = [];
  for (let i = 1; i <= 24; i += 1) {
    const level = props['level' + i];
    if (!Array.isArray(level)) continue;
    const coeff = num(level[0]);
    // Rounded to 10 decimals so 200 + (100 - 200) * 0.382 reads 161.8 rather than 161.79999999999998.
    const price = span && coeff !== null ? Math.round((span.from + (span.to - span.from) * coeff) * 1e10) / 1e10 : null;
    levels.push({ coeff, visible: level[2] === true, text: text(level[3]) || '', price });
  }
  return { id: String(shape.id), type: shape.name, points, levels, reverse };
});

function csvCell(value) {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : '';
}

function csvHeader(title) {
  return /[",\n\r]/.test(title) ? '"' + title.replace(/"/g, '""') + '"' : title;
}

const plotSets = ordered.map((source) => ({ data: source.data(), plots: exportedPlots(source.metaInfo()) }));
const header = ['time', 'open', 'high', 'low', 'close'];
plotSets.forEach((set) => set.plots.forEach((p) => header.push(p.title)));
const csvLines = [header.map(csvHeader).join(',')];
for (let i = bars.firstIndex(); i <= lastIndex; i += 1) {
  const bar = bars.valueAt(i);
  if (!bar) continue;
  const cells = [String(bar[0]), csvCell(bar[1]), csvCell(bar[2]), csvCell(bar[3]), csvCell(bar[4])];
  for (const set of plotSets) {
    const values = set.data && set.data.size() > 0 ? set.data.valueAt(i) : null;
    for (const p of set.plots) cells.push(values ? csvCell(values[p.column]) : '');
  }
  csvLines.push(cells.join(','));
}

return { identity, studies, drawings, series: { columns: header.length, rows: csvLines.length - 1, csv: csvLines.join('\n') } };
