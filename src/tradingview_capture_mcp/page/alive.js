// Standalone: is the chart API there yet? Polled while TradingView Desktop starts.
let symbol = null;
try {
  symbol = window.TradingViewApi.activeChart().symbol() || null;
} catch (e) {
  symbol = null;
}
return { api: typeof window.TradingViewApi, symbol };
