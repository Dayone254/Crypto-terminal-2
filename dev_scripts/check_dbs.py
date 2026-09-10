import os
import time

for db in ['tpt.db', 'backtest.db', 'tpt/data/backtest.db']:
    if os.path.exists(db):
        mtime = os.path.getmtime(db)
        print(f"{db}: {time.ctime(mtime)}")
    else:
        print(f"{db}: Not Found")
