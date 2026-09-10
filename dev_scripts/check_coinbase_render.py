from datetime import UTC, datetime

import httpx

url = "https://api.exchange.coinbase.com/products/RENDER-USD/candles"
start_iso = datetime.fromtimestamp(1788806135, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

res = httpx.get(url, params={"granularity": 900, "start": start_iso}, timeout=10.0)
print("Coinbase Status:", res.status_code)
if res.status_code == 200:
    candles = res.json()
    print(f"Fetched {len(candles)} candles from Coinbase:")
    for c in sorted(candles, key=lambda x: x[0])[:15]:
        c_time, c_low, c_high, c_open, c_close, vol = c
        c_iso = datetime.fromtimestamp(c_time, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        print(f"Candle Time: {c_iso} ({c_time}) | Open: {c_open} | High: {c_high} | Low: {c_low} | Close: {c_close}")
