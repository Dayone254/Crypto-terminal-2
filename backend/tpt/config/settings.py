from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/tpt
DEFAULT_DB_PATH = (BASE_DIR / "data" / "backtest.db").as_posix()

_SQLITE_PREFIXES = ("sqlite+aiosqlite:///", "sqlite:///")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — the ONE source of truth for the SQLite file location.
    # Every other module (raw signals layer, strategy-override loader) derives
    # its path from `sqlite_path` so the app can never split across DB files.
    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"

    # Exchange
    coinbase_api_base: str = "https://api.exchange.coinbase.com"

    # Scanner
    scan_interval_seconds: int = 300

    # Timezone
    display_tz: str = "Africa/Nairobi"

    # Server
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"

    # Optional shared-secret auth. When set, every /api request must carry
    # `X-API-Token: <value>`. Empty (default) = no auth, which is only safe
    # because the API binds to localhost by default.
    api_token: str = ""

    # Scoring: the config-driven strategy (strategy.yaml) is the default for ALL
    # symbols. The optional XGBoost model hard-codes options-flow inputs
    # (iv_skew, gamma_wall_proximity) that only exist for BTC/ETH, so enabling it
    # mis-scores every other coin. Off by default; opt in deliberately.
    enable_ml_scoring: bool = False

    # Live WebSocket L2 buffer. Each subscribed symbol costs three sockets
    # (Binance L2 + Coinbase L2 + ticker) and Windows' select() fails past
    # roughly 512 file descriptors, so the subscription set is hard-capped.
    max_ws_subscriptions: int = 20

    # Live WebSocket streaming (L2 depth + ticker). Requires an outbound network
    # path that permits WSS upgrades. When disabled, the scanner falls back to
    # the REST order-book snapshot and the /ws/* endpoints close immediately
    # rather than retrying handshakes forever.
    enable_live_ws: bool = False

    # Logging
    log_level: str = "INFO"
    log_file: str = "logs/tpt.jsonl"

    # Telegram (post-v1)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    @property
    def sqlite_path(self) -> str:
        """Filesystem path of the SQLite database, derived from `database_url`."""
        url = self.database_url
        for prefix in _SQLITE_PREFIXES:
            if url.startswith(prefix):
                return url[len(prefix):]
        # Non-SQLite backend (e.g. Postgres) — fall back to the default path so
        # callers still get a usable value.
        return DEFAULT_DB_PATH


settings = Settings()
