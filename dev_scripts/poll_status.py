import asyncio
import json

import httpx


async def poll():
    print("Polling API for scan completion...")
    async with httpx.AsyncClient(timeout=10) as c:
        while True:
            try:
                r = await c.get("http://localhost:8000/api/v1/scan/status")
                if r.status_code == 200:
                    d = r.json()
                    print("Current status:", d.get("status"))
                    if d.get("status") in ("DONE", "FAILED"):
                        with open("final_trace.json", "w") as f:
                            json.dump(d, f, indent=2)
                        print("Saved to final_trace.json")
                        break
            except Exception as e:
                print("Polling error:", e)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(poll())
