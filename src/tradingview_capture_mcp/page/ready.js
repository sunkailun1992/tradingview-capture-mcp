// A cheap fingerprint of the chart, polled after a switch until it settles.
const lastIndex = bars.lastIndex();
const lastBar = bars.valueAt(lastIndex);
const studies = orderedStudies().map((source) => {
  const data = source.data();
  const row = data && data.size() > 0 ? data.valueAt(lastIndex) : null;
  const cells = primitives(source, 'dwgtablecells', 'tableCells')
    .map((c) => [c.tid || 0, c.row, c.col, c.t])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  const labels = primitives(source, 'dwglabels', 'labels').map((l) => [l.x, l.y, l.t]);
  return {
    id: String(source.id()),
    name: studyName(source),
    status: studyStatus(source),
    lastTime: row ? row[0] : null,
    digest: JSON.stringify([row ? row.slice(1) : null, cells, labels]),
  };
});
return {
  symbol: chart.symbol(), listedSymbol: listedSymbol(), resolution: chart.resolution(),
  lastBarTime: lastBar ? lastBar[0] : null, studies,
};
