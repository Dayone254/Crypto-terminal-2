import traceback

import requests

try:
    print(requests.get('http://127.0.0.1:8002/api/v1/backtest/stats').text)
except Exception:
    traceback.print_exc()
