// TradingView's own rendering of the chart, as PNG bytes in base64.
const canvas = await TV.takeClientScreenshot();
const url = canvas.toDataURL('image/png');
return { width: canvas.width, height: canvas.height, base64: url.slice(url.indexOf(',') + 1) };
