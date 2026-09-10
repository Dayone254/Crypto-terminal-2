# Top Picker Terminal (TPT)

A local-first crypto market scanning terminal for Coinbase USD spot markets.

## What it does

- Scans Coinbase USD spot markets on a schedule
- Scores and labels each coin: **COILED / EARLY / CHASE / SKIP / WATCH / ENTRY_ZONE**
- Computes limit-order ladders (Tranche A + B, stop, targets)
- Fires quiet, deduplicated alerts only when price enters an actionable zone
- Displays results in a sortable Next.js dashboard

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (`pip install uv`)
- Node.js 20+ and npm (for the UI)

## Quick Start

```bash
# 1. Clone and enter the repo
cd "Crypto terminal 2"

# 2. Set up Python environment
cp .env.example .env
uv venv
uv pip install -e ".[dev]"

# 3. Create the database
make db-migrate

# 4. Run the backend (API + worker)
make serve

# 5. In a second terminal, run the UI
cd frontend && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

## CLI Usage

```bash
# Trigger an on-demand scan
tpt scan

# Scan with JSON output
tpt scan --output json

# Run database migrations
tpt db migrate

# Show current config
tpt config show
```

## Configuration

- **`.env`** — environment-level settings (DB path, ports, API base URL)
- **`config/strategy.yaml`** — scoring weights, label thresholds, alert rules. Hot-reloaded on each scan.

## Project Structure

```
├── backend/
│   └── tpt/              # Python package
│       ├── adapters/     # Exchange API clients
│       ├── engine/       # Pure scoring/labeling/ladder functions
│       ├── scanner/      # Scan orchestration + scheduler
│       ├── alerting/     # Alert generation + delivery
│       ├── api/          # FastAPI routes
│       ├── db/           # SQLAlchemy models + Alembic migrations
│       └── config/       # Settings + strategy config loader
├── frontend/             # Next.js TypeScript UI
├── config/
│   └── strategy.yaml     # Scoring/labeling/alert configuration
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   └── ROADMAP.md
├── tests/
│   ├── unit/
│   └── integration/
├── .env.example
├── Makefile
└── pyproject.toml
```

## Development

```bash
# Run tests
make test

# Lint
make lint

# Format
make format

# Type-check
make typecheck
```

## Project status & known limitations

**Working**
- Scheduled + on-demand scanning (`SCAN_INTERVAL_SECONDS`), with the scan results
  committed to SQLite and surfaced through `/api/v1/markets`.
- Config-driven scoring from `config/strategy.yaml`, hot-reloaded per scan run,
  with runtime weight overrides persisted via `PATCH /api/v1/config/scoring`.
- Limit-order ladders, labels/tags, and the backtest ledger + evaluator daemon.
- Alerting: zone entry/invalidation detection, watch lifecycle, dedupe keys,
  quiet hours, and the morning digest (`tpt/alerting/`). Telegram setup alerts.
- Alembic migrations (`make db-migrate`); the DB path comes from `DATABASE_URL`.

**Scoring & options flow**
- The config-driven strategy is the default for **all** symbols.
- Options-flow inputs (gamma walls, IV skew) only exist for underlyings with an
  options chain (BTC/ETH). For every other symbol those interactions are simply
  skipped, which is correct — they are *not* fed as neutral/zero values.
- The XGBoost model is **opt-in and off by default** (`ENABLE_ML_SCORING=true`).
  It hard-codes options inputs, so enabling it mis-scores non-options symbols.

**Security posture**
- The API binds to `127.0.0.1` by default and CORS is restricted to
  `FRONTEND_URL`. There is **no authentication** unless you set `API_TOKEN`
  (the UI reads `NEXT_PUBLIC_API_TOKEN`). Do not bind to `0.0.0.0` without it.

**Not built / not covered**
- No frontend test suite (type-check + production build only).
- `tpt/engine/feedback.py` (component hit-rate feedback) is not wired into the
  scoring loop.

## Non-goals (v1)

- No auto-trading or order placement
- No private API keys required or stored
- No mobile app
- No ML price prediction

## Docs

- [PRD](docs/PRD.md) — Full product requirements
- [Architecture](docs/ARCHITECTURE.md) — System design
- [Data Model](docs/DATA_MODEL.md) — Database schemas
- [Roadmap](docs/ROADMAP.md) — Milestones and timeline
