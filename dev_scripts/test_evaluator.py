import asyncio
import os
import sys

# Ensure backend root is in PYTHONPATH
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from tpt.engine.evaluator import process_signals


async def test_evaluator():
    print("Running process_signals...")
    try:
        await process_signals()
        print("process_signals completed successfully!")
    except Exception:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_evaluator())
