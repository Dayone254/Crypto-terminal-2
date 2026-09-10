import asyncio

import httpx


async def main():
    async with httpx.AsyncClient() as c:
        r = await c.get("https://api.exchange.coinbase.com/products/ETH-USD/stats")
        print(r.json())

if __name__ == "__main__":
    asyncio.run(main())
