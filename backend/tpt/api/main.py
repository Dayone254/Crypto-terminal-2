"""FastAPI application factory."""
from __future__ import annotations

import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tpt.api.routes import alerts, config, health, markets, scan, watchlist
from tpt.config.settings import settings
from tpt.db.connection import init_db

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure root logging so logger.* output actually lands somewhere.

    Previously LOG_FILE was declared but never wired up, so every log line in the
    scanner, evaluator and WS adapters was discarded.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.log_file:
        log_path = Path(settings.log_file)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
        except OSError as exc:  # pragma: no cover - filesystem dependent
            print(f"WARNING: could not open log file {log_path}: {exc}")
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
        force=False,
    )


_setup_logging()


async def _scan_scheduler_loop() -> None:
    """Run a market scan every SCAN_INTERVAL_SECONDS (0 disables)."""
    interval = settings.scan_interval_seconds
    if interval <= 0:
        logger.info("Scheduled scanning disabled (SCAN_INTERVAL_SECONDS=%s).", interval)
        return

    # Yield 10s on startup so FastAPI server completes startup & serves initial API requests
    await asyncio.sleep(10.0)
    logger.info("Scheduled scanning every %ss.", interval)
    while True:
        try:
            from tpt.scanner.runner import run_scan

            result = await run_scan(trigger="SCHEDULED")
            logger.info("Scheduled scan %s -> %s", result.scan_run_id, result.status)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Scheduled scan failed: %s", exc)

        # Delivery runs after each scan: undelivered alerts when outside quiet
        # hours, plus the morning digest for anything suppressed overnight.
        try:
            from tpt.alerting.delivery import deliver_morning_digest, deliver_pending_alerts

            await deliver_pending_alerts()
            await deliver_morning_digest()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Alert delivery failed: %s", exc)

        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Clean up any orphaned scans that were RUNNING when the server was killed
    from sqlalchemy import update

    from tpt.db.connection import AsyncSessionLocal
    from tpt.db.models import ScanRun

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(ScanRun)
            .where(ScanRun.status == "RUNNING")
            .values(status="FAILED", error_message="Server restarted during scan.")
        )
        await db.commit()

    from tpt.catalyst.daemon import catalyst_daemon_loop
    from tpt.engine.evaluator import evaluator_loop
    from tpt.engine.ws_memory import ws_memory

    # Options-flow cache (BTC/ETH gamma, IV skew) runs regardless of whether live
    # WebSocket streaming is enabled.
    options_task = ws_memory.start_options_daemon()

    tasks = [
        asyncio.create_task(evaluator_loop(), name="evaluator"),
        asyncio.create_task(_scan_scheduler_loop(), name="scan-scheduler"),
        asyncio.create_task(catalyst_daemon_loop(), name="catalyst-daemon"),
        options_task,
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Top Picker Terminal API",
        description="Crypto market scanner — Coinbase USD spot pairs.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Explicit allow-list. The previous `allow_origins=["*"]` combined with
    # allow_credentials is an invalid/dangerous combination that lets any page
    # the user visits call this API.
    allowed_origins = sorted({
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    })
    if settings.api_token:
        @application.middleware("http")
        async def enforce_api_token(request: Request, call_next):
            if (
                request.url.path.startswith("/api/")
                and request.headers.get("x-api-token") != settings.api_token
            ):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            return await call_next(request)

    # CORSMiddleware must be added LAST so it becomes the OUTERMOST middleware,
    # ensuring CORS headers (Access-Control-Allow-Origin) are attached to ALL responses,
    # including 500 Internal Server Errors, 504 Gateway Timeouts, and 401s.
    allowed_origins = sorted({
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    })
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    application.include_router(health.router, prefix="/api/v1", tags=["health"])
    application.include_router(markets.router, prefix="/api/v1", tags=["markets"])
    application.include_router(scan.router, prefix="/api/v1/scan", tags=["scan"])
    application.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
    application.include_router(config.router, prefix="/api/v1/config", tags=["config"])
    application.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["watchlist"])

    from tpt.api.routes import backtest, catalyst, research, ws_candles, ws_l2, ws_options
    application.include_router(ws_l2.router, prefix="/api/v1/ws/l2", tags=["websockets"])
    application.include_router(ws_candles.router, prefix="/api/v1/ws/candles", tags=["websockets"])
    application.include_router(ws_options.router, prefix="/api/v1/ws/options", tags=["websockets"])
    application.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])
    application.include_router(research.router, prefix="/api/v1/research", tags=["research"])
    application.include_router(catalyst.router, prefix="/api/v1/catalyst", tags=["catalyst"])

    return application


app = create_app()
