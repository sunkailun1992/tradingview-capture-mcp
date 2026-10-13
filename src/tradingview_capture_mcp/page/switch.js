// The only script that changes the chart: it sets the resolution and the symbol.
const target = ARGS.symbol;
const timeframe = ARGS.timeframe;
const waitMs = ARGS.waitMs || 20000;

// Resolves false when the chart calls back, true when it never does within waitMs.
function settle(start) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(true), waitMs);
    start(() => {
      clearTimeout(timer);
      resolve(false);
    });
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
return { before, after: { symbol: chart.symbol(), resolution: chart.resolution() }, timedOut };
