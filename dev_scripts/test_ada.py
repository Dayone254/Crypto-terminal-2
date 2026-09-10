import asyncio

from tpt.adapters.coinbase import CoinbaseAdapter


async def main():
    ada = CoinbaseAdapter()
    p = await ada.get_products()
    print("TOTAL PRODUCTS:", len(p))
    if p:
        print("FIRST TWO:", [x["id"] for x in p[:2]])
    await ada.close()

if __name__ == "__main__":
    asyncio.run(main())
