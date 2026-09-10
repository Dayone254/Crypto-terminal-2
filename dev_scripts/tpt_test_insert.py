import asyncio
import json

from tpt.data.database import get_connection


async def main():
    try:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO signals 
                (scan_run_id, symbol, timestamp, score, score_breakdown, label, trade_direction, entry_price, tp_price, tp2_price, sl_price) 
                VALUES (?, ?, strftime('%s', 'now'), ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "test_uuid",
                    "PAXG-USD", 
                    93.0, 
                    json.dumps({}),
                    "ENTRY_ZONE", 
                    "LONG",
                    10.0, 
                    12.0, 
                    14.0,
                    8.0
                )
            )
            await conn.commit()
            print("INSERT OK")
    except Exception as e:
        print("FAIL:", e)

    try:
        async with get_connection() as conn:
            async with conn.execute("SELECT * FROM signals WHERE symbol='PAXG-USD'") as cur:
                print("ROWS:", await cur.fetchall())
    except Exception:
        pass

if __name__ == "__main__":
    asyncio.run(main())
