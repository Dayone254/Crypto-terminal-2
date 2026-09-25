import asyncio
from tpt.engine.evaluator import process_signals
import logging
import time

logging.basicConfig(level=logging.INFO)

async def main():
    print("Running evaluator to clear legacy PENDING backlog...")
    start = time.time()
    await process_signals()
    print(f"Done in {time.time() - start:.2f} seconds.")

if __name__ == "__main__":
    asyncio.run(main())
