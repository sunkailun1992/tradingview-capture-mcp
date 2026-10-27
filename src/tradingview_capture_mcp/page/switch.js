// The only script that changes the chart: it sets the resolution and the symbol.
const target = ARGS.symbol;
const timeframe = ARGS.timeframe;
const waitMs = ARGS.waitMs || 20000;

// Resolves false when the chart calls back or the promise it returns settles, true when neither happens within
// waitMs, so a chart API that answers only with the promise does not wait out every switch.
function settle(start) {
  return new Promise((resolve) => {
    let timer = null;
    const finish = (timedOut) => {
      if (timer === null) return;
      clearTimeout(timer);
      timer = null;
      resolve(timedOut);
    };
    timer = setTimeout(() => finish(true), waitMs);
    const returned = start(() => finish(false));
    if (returned && typeof returned.then === 'function') returned.then(() => finish(false), () => finish(false));
  });
}

const before = { symbol: chart.symbol(), resolution: chart.resolution() };
let timedOut = false;
if (timeframe && chart.resolution() !== timeframe) {
  timedOut = (await settle((done) => chart.setResolution(timeframe, done))) || timedOut;
}
if (chart.symbol() !== target) {
  timedOut = (await settle((done) => chart.setSymbol(target, done))) || timedOut;
}
return { before, after: { symbol: chart.symbol(), listedSymbol: listedSymbol(), resolution: chart.resolution() }, timedOut };
