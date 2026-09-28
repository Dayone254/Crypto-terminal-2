@echo off
cd /d "F:\Crypto terminal 2"
set DATABASE_URL=sqlite+aiosqlite:///F:/Crypto terminal 2/backend/tpt/data/sandbox.db
set TELEGRAM_BOT_TOKEN=
set TELEGRAM_CHAT_ID=
set API_TOKEN=
set API_HOST=127.0.0.1
set API_PORT=8000
".venv\Scripts\python.exe" -m uvicorn tpt.api.main:app --host 127.0.0.1 --port 8000 > backend_sandbox.log 2>&1
