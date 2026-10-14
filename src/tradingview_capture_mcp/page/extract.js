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

function propertyNodes(source) {
  try {
    return source.properties().childs() || {};
  } catch (e) {
    return {};
  }
}

// Whole property nodes (palettes, fills, bands) are read with state(), single flags with value(); a node that is
// missing or throws reads as null rather than stopping the read.
function stateOf(node) {
  try {
    return node && typeof node.state === 'function' ? plain(node.state()) : null;
  } catch (e) {
    return null;
  }
}

function flagOf(node) {
  try {
    const value = node && typeof node.value === 'function' ? node.value() : null;
    return typeof value === 'boolean' ? value : null;
  } catch (e) {
    return null;
  }
}

// Live plot properties (colour, plot type, location, display); missing ones stay null rather than stopping the read.
function plotStyles(nodes) {
  try {
    const styles = nodes.styles.childs();
    const out = {};
    for (const [plotId, node] of Object.entries(styles)) {
      const fields = node && typeof node.childs === 'function' ? node.childs() : {};
      out[plotId] = {};
      for (const key of ['color', 'plottype', 'location', 'display']) {
        const child = fields[key];
        if (child && typeof child.value === 'function') out[plotId][key] = plain(child.value());
      }
    }
    return out;
  } catch (e) {
    return {};
  }
}

// A script compiled with RGB colours (metaInfo isRGB) stores a colour as a number holding ARGB, alpha in the top byte;
// other scripts store a value that the palette's valToIndex table turns into one of the palette's colour slots, and
// their tables, labels and lines use the shared palette_common (TradingView Desktop 3.4.1, probed 2026-10-14).
function rgba(value) {
  const v = value >>> 0;
  const alpha = Math.round((((v >>> 24) & 255) / 255) * 100) / 100;
  return 'rgba(' + ((v >>> 16) & 255) + ',' + ((v >>> 8) & 255) + ',' + (v & 255) + ',' + alpha + ')';
}

// Returns a CSS colour, null for no colour (na), or undefined when the value has no colour in the palette.
function colorResolver(meta, nodes) {
  const live = stateOf(nodes.palettes) || {};
  const defaults = (meta.defaults && meta.defaults.palettes) || {};
  return (value, paletteId) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    if (meta.isRGB === true) return rgba(value);
    const id = paletteId || 'palette_common';
    const definition = (meta.palettes || {})[id];
    const slot = definition && definition.valToIndex ? definition.valToIndex[value] : value;
    if (slot === undefined || slot === null) return undefined;
    const pick = (palettes) => palettes[id] && palettes[id].colors && palettes[id].colors[slot];
    const entry = pick(live) || pick(defaults);
    return entry && typeof entry.color === 'string' ? entry.color : undefined;
  };
}

// One colour per bar would repeat itself, so a colorer becomes runs of [first bar time, last bar time, colour] over
// the loaded bars; a colour the palette cannot name is counted in `unresolved` and written as null.
function colorRuns(data, column, resolve, paletteId) {
  const runs = [];
  let unresolved = 0;
  for (let i = bars.firstIndex(); i <= lastIndex; i += 1) {
    const bar = bars.valueAt(i);
    if (!bar) continue;
    const row = data && data.size() > 0 ? data.valueAt(i) : null;
    let color = resolve(row ? row[column] : null, paletteId);
    if (color === undefined) {
      unresolved += 1;
      color = null;
    }
    const open = runs[runs.length - 1];
    if (open && open[2] === color) open[1] = bar[0];
    else runs.push([bar[0], bar[0], color]);
  }
  return { runs, unresolved };
}

// The last bar where a plot has a value. A line that stopped before the last bar keeps showing this value on the
// price scale, so callers that read the axis need it as much as the last bar's value.
function lastValid(data, column) {
  if (!data || data.size() === 0) return null;
  for (let i = lastIndex; i >= bars.firstIndex(); i -= 1) {
    const row = data.valueAt(i);
    const value = row ? num(row[column]) : null;
    if (value !== null) return { time: row[0], value };
  }
  return null;
}

// Graphics kinds the export reads, plus script statistics that are not drawings.
const READ_GRAPHICS = new Set(['dwgtablecells', 'dwgtables', 'dwglabels', 'dwglines', 'dwgboxes', 'performance']);

// Items in a primitives collection, whichever of the two layouts it uses; an unknown non-empty layout counts as one
// so that it is reported rather than taken for empty.
function itemCount(collection) {
  let count = 0;
  try {
    for (const outer of collection.values()) {
      const inner = outer && typeof outer.get === 'function' ? outer.get(false) || outer : outer;
      const byId = inner && inner._primitivesDataById;
      if (byId && typeof byId.size === 'number') count += byId.size;
      else if (inner && typeof inner.size === 'number') count += inner.size;
      else if (inner) count += 1;
    }
  } catch (e) {
    return 0;
  }
  return count;
}

// What a study holds that the export leaves out, so a caller never takes a missing part for an empty one.
function notExportedOf(source, meta) {
  const all = (source._graphics && source._graphics._primitivesCollection) || {};
  return {
    plots: meta.plots.filter((p) => p.type === 'data').map((p) => ({ id: p.id, type: p.type, target: p.target || null })),
    graphics: Object.keys(all).filter((key) => !READ_GRAPHICS.has(key) && itemCount(all[key]) > 0),
  };
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
  const nodes = propertyNodes(source);
  const resolve = colorResolver(meta, nodes);
  const css = (value) => resolve(value) || null;
  const tables = new Map();
  const cellColors = new Map();
  for (const cell of primitives(source, 'dwgtablecells', 'tableCells')) {
    const id = String(cell.tid || 0);
    if (!tables.has(id)) {
      tables.set(id, []);
      cellColors.set(id, []);
    }
    const rows = tables.get(id);
    const colorRows = cellColors.get(id);
    while (rows.length <= cell.row) {
      rows.push([]);
      colorRows.push([]);
    }
    const row = rows[cell.row];
    const colorRow = colorRows[cell.row];
    while (row.length <= cell.col) {
      row.push(null);
      colorRow.push(null);
    }
    row[cell.col] = text(cell.t);
    colorRow[cell.col] = { text: css(cell.tc), background: css(cell.bgc) };
  }
  const positions = new Map(primitives(source, 'dwgtables', 'tables').map((t) => [String(t.id), t.pos || null]));
  const at = (x) => graphicsBar(source, x);
  const labels = primitives(source, 'dwglabels', 'labels').map((l) => ({
    id: l.id, index: at(l.x), time: barTime(at(l.x)), price: num(l.y), text: text(l.t) || '',
    style: l.st || null, color: l.ci === undefined ? null : l.ci, textColor: l.tci === undefined ? null : l.tci,
    size: l.sz || null, tooltip: l.tt || null, yloc: l.yl || null, textAlign: l.ta || null,
    colorCss: css(l.ci), textColorCss: css(l.tci),
  }));
  const lines = primitives(source, 'dwglines', 'lines').map((l) => ({
    id: l.id, index1: at(l.x1), time1: barTime(at(l.x1)), price1: num(l.y1),
    index2: at(l.x2), time2: barTime(at(l.x2)), price2: num(l.y2),
    extend: l.ex || null, style: l.st === undefined ? null : l.st, color: l.ci === undefined ? null : l.ci,
    width: l.w === undefined ? null : l.w, colorCss: css(l.ci),
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
  const liveStyles = plotStyles(nodes);
  // Pine v6 force_overlay: the plot draws on the main chart pane although its study sits in another pane. The live
  // chart keeps these ids in a Set, candle parts included; a candle group also carries the flag itself.
  const forceIds = meta._forceOverlayPlotIds;
  const forced = new Set(forceIds && typeof forceIds[Symbol.iterator] === 'function' ? Array.from(forceIds) : []);
  const plots = exportedPlots(meta).map((p, i) => {
    const plot = meta.plots[p.column - 1];
    const style = (meta.styles || {})[plot.id] || {};
    const live = liveStyles[plot.id] || {};
    const candle = (meta.ohlcPlots || {})[plot.target] || {};
    return {
      id: plot.id, title: p.title, type: plot.type, csvColumn: csvOffsets[studyIndex] + i,
      plotType: live.plottype === undefined ? null : live.plottype,
      location: live.location === undefined ? null : live.location,
      color: live.color === undefined ? null : live.color,
      text: typeof style.text === 'string' && style.text !== '' ? style.text : null,
      size: style.size || null, hidden: style.isHidden === true,
      display: typeof live.display === 'number' ? live.display : null,
      forceOverlay: forced.has(plot.id) || style.forceOverlay === true || candle.forceOverlay === true,
      lastValid: lastValid(data, p.column),
    };
  });
  // Every colorer: per-bar colours of a plot, a fill, a candle (target) or of the bars and background (no target).
  const colors = [];
  meta.plots.forEach((plot, index) => {
    if (!/colorer$/.test(plot.type)) return;
    const { runs, unresolved } = colorRuns(data, index + 1, resolve, plot.palette);
    colors.push({ id: plot.id, kind: plot.type, target: plot.target || null, runs, unresolved });
  });
  const fillStyles = stateOf(nodes.filledAreasStyle) || {};
  const fills = (meta.filledAreas || []).map((f) => {
    const live = fillStyles[f.id] || {};
    return {
      id: f.id, title: f.title || null, type: f.type || null, between: [f.objAId || null, f.objBId || null],
      visible: live.visible !== false && f.isHidden !== true, fillType: live.fillType || null,
      color: typeof live.color === 'string' ? live.color : null, transparency: num(live.transparency),
    };
  });
  const bandStyles = stateOf(nodes.bands) || [];
  const bands = (meta.bands || []).map((b, i) => {
    const live = bandStyles[i] || {};
    return {
      id: b.id, name: b.name || null, value: num(live.value), color: typeof live.color === 'string' ? live.color : null,
      visible: live.visible !== false && b.isHidden !== true, lineStyle: num(live.linestyle), lineWidth: num(live.linewidth),
    };
  });
  return {
    id: String(source.id()), name: studyName(source), pane: paneIndexOf(source), status: studyStatus(source), inputs,
    visible: flagOf(nodes.visible), showLabelsOnPriceScale: flagOf(nodes.showLabelsOnPriceScale),
    // How the study's values are printed, e.g. { type: 'volume' } shows 83424 as 83.42K on the price scale.
    format: plain(meta.format || null),
    tables: Array.from(tables, ([id, rows]) => ({ id, position: positions.get(id) || null, rows, cellColors: cellColors.get(id) })),
    labels, lines, boxes, lastValues, plots, colors, fills, bands, notExported: notExportedOf(source, meta),
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
