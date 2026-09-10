import asyncio

from tpt.adapters.coinbase import CoinbaseAdapter
from tpt.engine.features import compute_features
from tpt.engine.scorer import score
from tpt.engine.ws_memory import ws_memory


async def audit():
    # Warm up Options Cache
    print("Warming up Deribit Options Cache...")
    try:
        from tpt.engine.options_flow import calculate_macro_gamma_exposure
        btc_flow = await calculate_macro_gamma_exposure("BTC", 0.0)
        ws_memory.macro_options_cache["BTC"] = btc_flow
    except Exception as e:
        print(f"Options sync error: {e}")

    adapter = CoinbaseAdapter()
    
    # Manually testing top-performing Altcoins vs BTC
    symbols = ['NEAR-USD', 'ZEC-USD']
    print(f"Bypassing empty local database. Manually feeding {symbols} into the AI engine...")

    btc_stats = await adapter.get_stats('BTC-USD')
    btc_day_change = ((float(btc_stats.get('last',0)) - float(btc_stats.get('open',0))) / float(btc_stats.get('open',1))) * 100 if btc_stats.get('open') else 0.0
    print(f"Global Baseline: BTC is currently running {btc_day_change:.2f}%")

    for symbol in symbols:
        st = await adapter.get_stats(symbol)
        if not st or 'last' not in st: 
            print(f"Skipping {symbol} (no stats)")
            continue
        
        feats = compute_features(
            raw_stats=st,
            raw_ticker=st,
            btc_day_change_pct=btc_day_change
        )
        feats['product_id'] = symbol
        
        direction = "LONG"
        new_score = score(feats, trade_direction=direction)
        
        print('-'*50)
        print(f'[{symbol}] {direction}')
        day_chg = ((float(st.get('last',0)) - float(st.get('open',0))) / float(st.get('open',1))) * 100
        print(f'  Asset Performance : {day_chg:.2f}%')
        print(f'  TapeRadar Score   : {new_score["clamped"]}')
        
        rs_val = feats.get("rs_vs_btc", 0.0)
        if rs_val is not None:
            print(f'  RS vs BTC Filter  : {rs_val:.2f}%')
            
        print('  Quantitative ML Footprint (New Modifiers):')
        found_mods = False
        for k,v in new_score.get('components', {}).items():
            if 'rs_btc' in k or 'gamma' in k or 'skew' in k:
                print(f'    -> {k}: {v} points')
                found_mods = True
        if not found_mods:
            print("    -> (No edge found)")
                
asyncio.run(audit())
