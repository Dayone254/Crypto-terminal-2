import asyncio
import os
import sys

import httpx

# Ensure backend root is in PYTHONPATH
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

import sqlite3

from tpt.engine.evaluator import _fetch_candles


async def test_fetch():
    db_path = os.path.join(os.path.dirname(__file__), 'tpt', 'data', 'backtest.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, symbol, timestamp FROM signals WHERE status='PENDING' ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    
    if not row:
        print("No PENDING signals found.")
        return
        
    symbol = row['symbol']
    fetch_from = row['timestamp']
    print(f"Testing {symbol} at timestamp {fetch_from}...")
    
    async with httpx.AsyncClient() as client:
        candles = await _fetch_candles(client, symbol, fetch_from)
        print(f"Got {len(candles)} candles!")
        if candles:
            print("First:", candles[0])
            print("Last: ", candles[-1])

if __name__ == "__main__":
    asyncio.run(test_fetch())
