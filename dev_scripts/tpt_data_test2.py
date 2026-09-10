import asyncio
import traceback

from tpt.data.database import get_connection


async def test():
    try:
        async with await get_connection() as conn:
            async with conn.execute("SELECT status, COUNT(*) as cnt FROM signals GROUP BY status") as cursor:
                rows = await cursor.fetchall()
                counts = {"PENDING": 0, "WIN": 0, "LOSS": 0}
                for r in rows:
                    counts[r["status"]] = r["cnt"]
                    
                total_closed = counts["WIN"] + counts["LOSS"]
                win_rate = (counts["WIN"] / total_closed * 100) if total_closed > 0 else 0.0
                
                async with conn.execute("SELECT * FROM signals WHERE status IN ('WIN', 'LOSS') ORDER BY id DESC LIMIT 50") as cursor:
                    recent_trades = [dict(r) for r in await cursor.fetchall()]
                    
                async with conn.execute("SELECT * FROM signals WHERE status = 'PENDING' ORDER BY id DESC") as cursor:
                    pending_trades = [dict(r) for r in await cursor.fetchall()]
                    
                print("SUCCESS")
    except Exception:
        print("FAILED")
        traceback.print_exc()

asyncio.run(test())
