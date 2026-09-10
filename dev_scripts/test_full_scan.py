import asyncio
import traceback

from tpt.scanner.runner import run_scan


async def main():
    try:
        r = await run_scan()
        print("STATUS:", r.status)
        if r.error_message:
            print("ERROR", r.error_message)
    except Exception:
        with open("traceback_final.txt", "w") as f:
            traceback.print_exc(file=f)

if __name__ == "__main__":
    asyncio.run(main())
