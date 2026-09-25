import asyncio
from tpt.db.connection import AsyncSessionLocal
from sqlalchemy import select
from tpt.db.models import ScanRun, Score

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(ScanRun.id)
            .where(ScanRun.status == "DONE")
            .order_by(ScanRun.started_at.desc())
            .limit(1)
        )
        latest_done_id = res.scalar_one_or_none()
        print("LATEST DONE SCAN RUN ID:", latest_done_id)

        if latest_done_id:
            scores_res = await db.execute(
                select(Score)
                .where(Score.scan_run_id == latest_done_id)
            )
            scores = scores_res.scalars().all()
            print("SCORES COUNT FOR LATEST DONE SCAN RUN:", len(scores))

if __name__ == "__main__":
    asyncio.run(main())
