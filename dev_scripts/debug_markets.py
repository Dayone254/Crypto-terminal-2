import asyncio

from tpt.api.routes.markets import list_markets


async def main():
    try:
        res = await list_markets()
        print("Success! Items:", len(res))
    except Exception as e:
        print("EXCEPTION TYPE:", type(e))
        if hasattr(e, 'orig'):
            print("ORIGINAL DB ERROR:", e.orig)
        else:
            print("FULL REPR:", repr(e))

if __name__ == "__main__":
    asyncio.run(main())
