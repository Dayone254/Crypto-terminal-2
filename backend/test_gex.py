import asyncio
import json
import sys

sys.path.insert(0, "f:/Crypto terminal 2/backend")

from tpt.engine.options_flow import calculate_macro_gamma_exposure

async def main():
    for symbol in ["BTC", "ETH", "SOL", "AVAX"]:
        print(f"\n==================== {symbol} ====================")
        for exp in ["ALL", "0DTE", "7D", "30D"]:
            res = await calculate_macro_gamma_exposure(symbol, 0.0, exp)
            print(f"[{exp:4}] GEX: {res.get('total_net_gex_millions'):6.2f}M | CallWall: ${res.get('call_wall'):<8} | PutWall: ${res.get('put_wall'):<8} | Flip: ${res.get('gamma_flip'):<8}")

if __name__ == "__main__":
    asyncio.run(main())
