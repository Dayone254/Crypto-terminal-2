from datetime import UTC, datetime, timedelta

import httpx

url = "https://api.exchange.coinbase.com/products/RENDER-USD/candles"
start_dt = datetime.fromtimestamp(1788806135, tz=UTC)
end_dt = start_dt + timedelta(hours=24)

start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"Requesting start={start_iso}, end={end_iso}")
res = httpx.get(url, params={"granularity": 900, "start": start_iso, "end": end_iso}, timeout=10.0)
print("Status:", res.status_code)
if res.status_code == 200:
    candles = res.json()
    print(f"Returned {len(candles)} candles:")
    for c in sorted(candles, key=lambda x: x[0])[:15]:
        c_time, c_low, c_high, c_open, c_close, vol = c
        c_iso = datetime.fromtimestamp(c_time, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {c_iso} ({c_time}) | Open: {c_open} | High: {c_high} | Low: {c_low} | Close: {c_close}")
