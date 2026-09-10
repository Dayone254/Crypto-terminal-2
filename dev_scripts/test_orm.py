import asyncio
import time

from sqlalchemy import select

from tpt.db.connection import AsyncSessionLocal
from tpt.db.models import Feature, Ladder, ScanRun, Score, Symbol


async def run():
    async with AsyncSessionLocal() as db:
        t0 = time.time()
        scan_res = await db.execute(
            select(ScanRun)
            .where(ScanRun.status == "DONE")
            .order_by(ScanRun.started_at.desc())
            .limit(1)
        )
        latest_scan = scan_res.scalar_one_or_none()
        if not latest_scan:
            print("No scan")
            return
            
        print(f"Scan ID {latest_scan.id} took {time.time()-t0:.2f}s")
        
        stmt = (
            select(Score, Feature, Ladder, Symbol)
            .join(Feature, (Score.product_id == Feature.product_id) & (Score.scan_run_id == Feature.scan_run_id))
            .outerjoin(Ladder, (Score.product_id == Ladder.product_id) & (Score.scan_run_id == Ladder.scan_run_id))
            .outerjoin(Symbol, Score.product_id == Symbol.product_id)
            .where(Score.scan_run_id == latest_scan.id)
            .order_by(Score.composite_score.desc())
        )
        t1 = time.time()
        res = await db.execute(stmt)
        rows = res.all()
        print(f"Executing query and fetching took {time.time()-t1:.2f}s")
        print(f"Number of rows: {len(rows)}")

asyncio.run(run())
