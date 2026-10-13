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
};

function plain(value) {
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (e) {
    return null;
  }
}

const ordered = orderedStudies();
const studies = ordered.map((source) => {
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
  const labels = primitives(source, 'dwglabels', 'labels').map((l) => ({
    id: l.id, index: l.x, time: barTime(l.x), price: num(l.y), text: text(l.t) || '',
    style: l.st || null, color: l.ci === undefined ? null : l.ci, textColor: l.tci === undefined ? null : l.tci,
    size: l.sz || null, tooltip: l.tt || null,
  }));
  const lines = primitives(source, 'dwglines', 'lines').map((l) => ({
    id: l.id, index1: l.x1, time1: barTime(l.x1), price1: num(l.y1), index2: l.x2, time2: barTime(l.x2), price2: num(l.y2),
    extend: l.ex || null, style: l.st === undefined ? null : l.st, color: l.ci === undefined ? null : l.ci,
    width: l.w === undefined ? null : l.w,
  }));
  const boxes = primitives(source, 'dwgboxes', 'boxes').map((b) => plain(b) || { id: b.id });
  const data = source.data();
  const row = data && data.size() > 0 ? data.valueAt(lastIndex) : null;
  const lastValues = exportedPlots(meta).map((p) => [p.title, row ? num(row[p.column]) : null]);
  let inputs = null;
  try {
    inputs = source.inputs ? plain(source.inputs()) : null;
  } catch (e) {
    inputs = null;
  }
  return {
    id: String(source.id()), name: studyName(source), pane: paneIndexOf(source), status: studyStatus(source), inputs,
    tables: Array.from(tables, ([id, rows]) => ({ id, rows })), labels, lines, boxes, lastValues,
  };
});

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
  const levels = [];
  for (let i = 1; i <= 24; i += 1) {
    const level = props['level' + i];
    if (Array.isArray(level)) levels.push({ coeff: num(level[0]), visible: level[2] === true, text: text(level[3]) || '' });
  }
  return { id: String(shape.id), type: shape.name, points, levels, reverse: props.reverse === true };
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
