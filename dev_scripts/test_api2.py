import asyncio

import httpx


async def run():
    async with httpx.AsyncClient() as client:
        res = await client.get('http://localhost:8000/api/v1/markets')
        data = res.json()
        cands = data.get("candidates", [])
        print(f"Total returned candidates: {len(cands)}")
        if cands:
            for i in range(min(5, len(cands))):
                c = cands[i]
                print(f"{c['product_id']} | Score: {c.get('composite_score')} | Label: {c.get('label')}")

asyncio.run(run())
