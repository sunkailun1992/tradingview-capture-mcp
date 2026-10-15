// Reports the main series' loaded bars and, when ARGS.request is a positive count, asks TradingView for that many
// older bars, as scrolling left does. Besides switch.js the only script that changes the chart: it adds older bars to
// what is loaded and leaves the view, the zoom, studies and drawings alone; the next switch drops them again.
// Relies on the main series' requestMoreData, requestMoreDataAvailable, isLoading and endOfDataType (TradingView
// Desktop 3.4.1, probed 2026-10-15).
const series = model.mainSeries();
const missing = ['requestMoreData', 'requestMoreDataAvailable', 'endOfDataType', 'isLoading']
  .filter((name) => typeof series[name] !== 'function');
if (missing.length) throw new Error('TV_INTERNALS_CHANGED: the main series lacks ' + missing.join(', '));

const size = bars.size();
const first = size > 0 ? bars.valueAt(bars.firstIndex()) : null;
const last = size > 0 ? bars.valueAt(bars.lastIndex()) : null;
const state = {
  symbol: chart.symbol(),
  resolution: chart.resolution(),
  bars: size,
  firstBarTime: first ? first[0] : null,
  lastBarTime: last ? last[0] : null,
  loading: series.isLoading() === true,
  canRequest: series.requestMoreDataAvailable() === true,
  // The data_completed flag of the server's last answer, e.g. 'limit' once it sends nothing older.
  endOfData: series.endOfDataType() || null,
  requested: 0,
};
const count = ARGS.request;
if (Number.isInteger(count) && count > 0 && !state.loading && state.canRequest && state.endOfData === null) {
  series.requestMoreData(count);
  // The series returns quietly while it is not ready; a request it sent marks it loading.
  if (series.isLoading() === true || series.requestMoreDataAvailable() !== true) state.requested = count;
}
return state;
