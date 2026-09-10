import sqlite3
from datetime import UTC, datetime

import httpx

conn = sqlite3.connect('tpt/data/backtest.db')
conn.row_factory = sqlite3.Row
sig = dict(conn.execute("SELECT * FROM signals WHERE id=185").fetchone())

sig_ts = sig['timestamp']
sig_iso = datetime.fromtimestamp(sig_ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
print(f"Signal 185 created at: {sig_iso} ({sig_ts})")

url = "https://api.exchange.coinbase.com/products/RENDER-USD/candles"
# Test 1: Only start
res1 = httpx.get(url, params={"granularity": 900, "start": datetime.fromtimestamp(sig_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")})
candles1 = sorted(res1.json(), key=lambda x: x[0]) if res1.status_code==200 else []
print(f"\nTest 1 (Only start) returned {len(candles1)} candles:")
if candles1:
    print("  First candle:", datetime.fromtimestamp(candles1[0][0], tz=UTC).strftime("%Y-%m-%d %H:%M:%S"), f"({candles1[0][0]})")
    print("  Last candle: ", datetime.fromtimestamp(candles1[-1][0], tz=UTC).strftime("%Y-%m-%d %H:%M:%S"), f"({candles1[-1][0]})")

# Test 2: Both start and end
now_dt = datetime.now(UTC)
res2 = httpx.get(url, params={"granularity": 900, "start": datetime.fromtimestamp(sig_ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "end": now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")})
candles2 = sorted(res2.json(), key=lambda x: x[0]) if res2.status_code==200 else []
print(f"\nTest 2 (Both start & end) returned {len(candles2)} candles:")
if candles2:
    print("  First candle:", datetime.fromtimestamp(candles2[0][0], tz=UTC).strftime("%Y-%m-%d %H:%M:%S"), f"({candles2[0][0]})")
    print("  Last candle: ", datetime.fromtimestamp(candles2[-1][0], tz=UTC).strftime("%Y-%m-%d %H:%M:%S"), f"({candles2[-1][0]})")
