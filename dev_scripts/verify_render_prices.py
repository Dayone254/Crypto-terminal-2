from datetime import UTC, datetime

import httpx

url = "https://api.exchange.coinbase.com/products/RENDER-USD/candles"
start_iso = "2026-09-07T18:35:35Z"
end_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

res = httpx.get(url, params={"granularity": 900, "start": start_iso, "end": end_iso}, timeout=10.0)
candles = sorted(res.json(), key=lambda x: x[0])

print(f"Post-signal candle count: {len(candles)}")
min_low = min(c[1] for c in candles)
max_high = max(c[2] for c in candles)
print(f"Post-signal MIN LOW: {min_low} | MAX HIGH: {max_high}")

for c in candles:
    c_iso = datetime.fromtimestamp(c[0], tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
    if c[1] <= 1.50:
        print(f"FOUND LOW < 1.50 at {c_iso}: Low={c[1]}")
