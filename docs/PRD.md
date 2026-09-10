# Product Requirements Document — Top Picker Terminal (TPT) v1

**Codename:** `tpt`
**Document version:** 1.1
**Date:** 2026-09-05 (updated 2026-09-05 — spec clarifications v1)
**Author:** (Engineering Lead / PM)
**Status:** DRAFT — v1.1 incorporates user clarifications on labeling, dedupe, pinned watches, process model, copy-ladder format

---

## Table of Contents

1. [Overview](#1-overview)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [Personas & Jobs-to-be-Done](#4-personas--jobs-to-be-done)
5. [User Stories](#5-user-stories)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Domain Model & Glossary](#8-domain-model--glossary)
9. [Scoring & Labeling Specification](#9-scoring--labeling-specification)
10. [Alerting & Dedupe Specification](#10-alerting--dedupe-specification)
11. [Data Model](#11-data-model)
12. [API Outline](#12-api-outline)
13. [UI Wireframe Description](#13-ui-wireframe-description)
14. [Risks & Open Questions](#14-risks--open-questions)
15. [Milestones & Acceptance Criteria](#15-milestones--acceptance-criteria)

---

## 1. Overview

**Top Picker Terminal (TPT)** is a local-first crypto market scanning tool for solo discretionary traders on the Coinbase exchange. It continuously fetches public market data, scores each USD spot pair for trade setup quality, computes structured limit-ladder entry zones (Tranche A + B), and fires quiet, de-duplicated alerts only when price newly enters an actionable zone.

TPT encodes a repeatable, rules-based discretionary workflow — not a black-box prediction engine — so the trader can audit every label, score, and level before acting.

---

## 2. Problem Statement

A solo trader watching Coinbase markets faces three compounding inefficiencies:

| Pain Point | Current Workaround | Cost |
|---|---|---|
| Manually scanning 100+ USD markets for setups | Scrolling exchange UI + bubble heatmaps | 30–60 min per scan cycle |
| No systematic filter for "chase" setups (overbought, late) | Gut feel + regret | Capital loss from FOMO entries |
| No pre-computed entry levels (retrace, VWAP pockets) | Drawing fib/VWAP in TradingView for each coin | 10–15 min per candidate |

The result is slow discovery, inconsistent labeling, and emotional entries near intraday tops.

---

## 3. Goals & Non-Goals

### 3.1 Goals (v1)

| # | Goal |
|---|---|
| G1 | Scan Coinbase USD spot pairs on a configurable schedule and on-demand |
| G2 | Compute features: 24h % change, position-in-range, 24h VWAP, quote volume, fib retraces, simple swing shelves |
| G3 | Score (0–100) and label each symbol: COILED / EARLY / CHASE / SKIP / WATCH / ENTRY_ZONE |
| G4 | Output a structured limit ladder (Tranche A 60%, Tranche B 40%, stop, 1–2 targets) for candidates |
| G5 | Persist snapshots and alert history in SQLite |
| G6 | Alert only on newly-entered A/B zones, with ~6h dedupe window; re-entry after confirmed zone exit resets dedupe |
| G7 | Display a sortable table + detail drawer with "copy ladder" text action |
| G8 | **Scans run 24/7.** Alert *delivery* is quiet 00:00–07:59 Nairobi; alerts queue for morning digest at 08:00 |
| G9 | Pinned-watch symbols (e.g. ZORA, HYPE, NEAR) receive A/B/break/invalidation alerts regardless of score threshold |

### 3.2 Non-Goals (v1)

- Order placement, auto-trading, or holding private API keys
- ML price prediction or neural network scoring
- Mobile application
- Multi-user SaaS or cloud hosting
- Guaranteeing profitable outcomes
- >50 indicators or signal soup

---

## 4. Personas & Jobs-to-be-Done

### Persona A — "Solo Nairobi Trader" (Primary)

| Attribute | Detail |
|---|---|
| Name / Handle | Kamau |
| Location & TZ | Nairobi, Africa/Nairobi (UTC+3) |
| Exchange Used | Coinbase (spot, USD-quoted pairs) |
| Experience | 3+ years discretionary crypto; reads structure and fib levels |
| Hardware | Windows laptop; intermittent internet |
| Session pattern | Morning scan 08:00–10:00, afternoon check 14:00–16:00, sometimes night owl |

**Jobs-to-be-Done:**

| JTBD | Job statement |
|---|---|
| J1 | When I wake up, I want to immediately know which coins are coiled for a move without manual scanning |
| J2 | When I see an alert, I want pre-computed entry levels so I can place limit orders in <2 min |
| J3 | When a coin is pumping, I want the system to flag it as CHASE so I resist FOMO |
| J4 | At end of day, I want to review which alerts fired and which played out |
| J5 | I want to sleep without missing a zone re-test during off-hours (silent alert queue) |

### Persona B — "Future Power User" (Secondary, post-v1)

A second discretionary trader who runs the terminal independently with different risk parameters. Requires multi-profile support — explicitly out of scope for v1.

---

## 5. User Stories

### P0 — Must-have for any usable release

| ID | Story | Acceptance Criteria |
|---|---|---|
| US-01 | As Kamau, I can trigger an on-demand full scan so that I see fresh scores without waiting for a schedule | Scan completes in < 30s for ≥100 liquid pairs; results visible in UI table |
| US-02 | As Kamau, I receive an alert when price newly enters a ladder Tranche A or B zone | Alert fires ≤ 60s after zone entry; payload includes symbol, zone type, price, levels |
| US-03 | As Kamau, I see each coin with a **single primary label** (COILED / EARLY / CHASE / SKIP / WATCH / ENTRY_ZONE) plus secondary tags so I always know exactly what rule fired | Labels derived from documented rule thresholds; reproducible from stored snapshot data |
| US-04 | As Kamau, I can view the limit ladder (A price, B price, stop, T1, T2) for any labeled candidate | Ladder visible in detail drawer; "Copy Ladder" copies formatted text to clipboard |
| US-05 | As Kamau, I am not spammed — the same zone alert doesn't repeat within 6h unless price **confirmed** exiting (≥EXIT_TOL for ≥2 consecutive snapshots) then re-entered | Dedupe + exit regression tests pass |
| US-06 | As Kamau, scans run 24/7 automatically; alert *delivery* is silenced 00:00–07:59 Nairobi; digest at 08:00 surfaces queued alerts | Scans continue during quiet window; alert count in digest matches suppressed count |
| US-07P | As Kamau, I can pin ZORA / HYPE / NEAR and receive A/B/breakout/invalidation alerts for them even if score < 70 | Pinned watch alerts fire for score < 70; non-pinned sub-threshold symbols do not alert |

### P1 — High value, v1 target

| ID | Story |
|---|---|
| US-07 | As Kamau, I can sort the market table by score, label, or 24h change to quickly find the best setups |
| US-08 | As Kamau, I can see the position-in-range bar so I can instantly see how close to the high each coin is |
| US-09 | As Kamau, the terminal persists recent scans so I can review what setups existed 4h ago |
| US-10 | As Kamau, I can filter the table by label (e.g., show only COILED and EARLY) |
| US-11 | As Kamau, I can configure the min volume threshold and scan interval in a YAML config without touching code |
| US-12 | As Kamau, I can replay the alert history log to audit every fired alert |

### P2 — Nice-to-have / future

| ID | Story |
|---|---|
| US-13 | As Kamau, I can add a coin to a watchlist to monitor it even when it doesn't meet score thresholds |
| US-14 | As Kamau, I can see a simple P&L tracker for trades I manually log against ladder levels |
| US-15 | As Kamau, I can connect MEXC as a second exchange source |
| US-16 | As Kamau, I can receive alerts via Telegram bot in addition to in-app |

---

## 6. Functional Requirements

### FR-01 — Market Universe

- **FR-01.1** The system SHALL fetch all active Coinbase USD spot products via `GET /products`.
- **FR-01.2** The system SHALL filter out products where `status != "online"` or `trading_disabled == true`.
- **FR-01.3** Liquid products are defined by `quote_volume_24h >= MIN_QUOTE_VOLUME` (default: $1,000,000 USD). This threshold is externally configurable.

### FR-02 — Data Ingestion

- **FR-02.1** For each symbol, fetch `GET /products/{id}/stats` (24h open, high, low, last, volume).
- **FR-02.2** For each symbol, fetch `GET /products/{id}/ticker` (bid, ask, price, volume).
- **FR-02.3** Candles (1h + 1d, last 300 periods) are fetched for: (a) symbols labeled COILED/EARLY/ENTRY_ZONE after Phase 1, AND (b) any pinned-watch symbol regardless of Phase-1 label, AND (c) BTC-USD always (needed for rs_vs_btc and RSI baseline). SKIP and non-pinned CHASE/WATCH symbols do NOT get candles.
- **FR-02.4** All fetched data SHALL be stored as a raw JSON snapshot keyed by `(symbol, utc_timestamp)`.
- **FR-02.5** The scanner SHALL rate-limit Coinbase REST calls to ≤3 requests per second per public endpoint to avoid 429s (see FR-09).

### FR-03 — Feature Computation

- **FR-03.1** `day_change_pct = ((last - open) / open) * 100`
- **FR-03.2** `pos_in_range = (last - day_low) / (day_high - day_low)` — clamped to [0, 1]; if `day_high == day_low`, return 0.5 (flat day guard).
- **FR-03.3** `quote_vol_24h = float(stats['volume']) * float(stats['last'])`. Coinbase `/stats` `volume` is **base-currency units** (e.g. BTC, ETH). Multiplying by last price converts to USD quote volume. This is the canonical formula. Acceptance test: `ZORA-USD stats.volume=1_200_000_000, last=0.00852 → quote_vol_24h ≈ $10.2M`.
- **FR-03.4** `vwap_24h` — if 1h candles fetched: `sum((h+l+c)/3 * vol for each candle) / sum(vol)`; else fallback `(day_high + day_low + last) / 3`.
- **FR-03.5** Fibonacci retraces computed from `(day_low, day_high)` impulse:
  - Retrace levels: 23.6%, 38.2%, 50%, 61.8%, 78.6%
  - Fib zone band for Tranche A: 50–61.8% retrace price
  - Fib zone band for Tranche B: 76.4–78.6% retrace price
- **FR-03.6** Swing shelf identified as: lowest pivot low in the last 7 days from 1d candles.
- **FR-03.7** 1h RSI (14-period Wilder's smoothing) is computed **only for symbols where candles are fetched** (per FR-02.3): COILED/EARLY/ENTRY_ZONE candidates + pinned symbols + BTC-USD. SKIP and non-pinned CHASE/WATCH receive `rsi_1h = NULL`. The `OVERBOUGHT_RSI_1H` score penalty is skipped when `rsi_1h IS NULL`.
- **FR-03.8** Relative strength vs BTC: `rs_btc = day_change_pct(symbol) - day_change_pct(BTC-USD)`.

### FR-04 — Scoring

See §9 for formula specification.

- **FR-04.1** Each symbol SHALL receive a composite score in range [0, 100].
- **FR-04.2** Score components and weights SHALL be stored in `config/strategy.yaml` and reloadable without restart.
- **FR-04.3** Each score record SHALL include a breakdown of component contributions for auditability.

### FR-05 — Labeling

See §9 for logic tree.

- **FR-05.1** Each symbol receives exactly **one primary label** determined by the ordered priority tree: `SKIP → CHASE → ENTRY_ZONE → COILED → EARLY → WATCH`. The first matching condition wins.
- **FR-05.2** In addition to the primary label, a symbol may carry zero or more **secondary tags** stored in `scores.tags` (JSON array). Tags describe conditions that are true but did not win the priority race. Examples: a symbol labelled EARLY that also meets VWAP confluence criteria gets tag `["VWAP_CONFLUENCE"]`; a COILED symbol touching its fib_500 gets `["FIB_TOUCH"]`. Tags appear in the detail drawer and are filterable in the UI.
- **FR-05.3** Labels and tags SHALL be re-evaluated on every scan run.
- **FR-05.4** Label thresholds SHALL be stored in `config/strategy.yaml`.
- **FR-05.5** A pinned symbol (per FR-12) retains its primary label normally — pinning does **not** override labeling. It only bypasses the score gate for alert generation.

### FR-06 — Ladder Computation

- **FR-06.1** Ladders are computed for: (a) symbols labeled COILED, EARLY, or ENTRY_ZONE, AND (b) any pinned-watch symbol whose candles were fetched, even if its score < 70 or its label is WATCH. Ladders are NOT generated for SKIP or CHASE labels.
- **FR-06.2** Tranche A (60% position size): set at the midpoint of the 50–61.8% fib zone or VWAP ± 0.5% pocket, whichever gives a lower price (more conservative entry).
- **FR-06.3** Tranche B (40% position size): set at the 78.6% fib retrace from day impulse or the 7d swing shelf, whichever is lower.
- **FR-06.4** Stop loss: `stop = tranche_b * (1 - STOP_PCT)`, default `STOP_PCT = 0.03` (configurable).
- **FR-06.5** Target 1: day high reclaim zone (`day_high * 0.995`).
- **FR-06.6** Target 2: prior 7d swing high (from 1d candles) if available; else `day_high * 1.05`.
- **FR-06.7** Chase rule: if `day_change_pct > 15 AND pos_in_range > 0.80`, label is CHASE; no ladder generated **even for pinned symbols**. Chase is an absolute block.

### FR-07 — Persistence

- **FR-07.1** All scan snapshots SHALL be persisted to SQLite (schemas in §11).
- **FR-07.2** Snapshots SHALL be retained for 30 days by default (configurable `SNAPSHOT_RETENTION_DAYS`).
- **FR-07.3** Alert history SHALL be retained for 90 days.
- **FR-07.4** A `user_settings` table SHALL hold per-key configuration overrides (min volume, quiet hours, etc.).

### FR-08 — Alerting

See §10 for full dedupe spec.

- **FR-08.1** Alerts SHALL fire only when price newly enters a ladder zone (Tranche A or B) within the current scan.
- **FR-08.2** "Newly enters" means: not flagged as in-zone in the previous scan result.
- **FR-08.3** Quiet hours suppress delivery but store an undelivered alert for digest.
- **FR-08.4** Morning digest (08:00 Nairobi) SHALL surface all undelivered alerts from the quiet window.
- **FR-08.5** Breakout watch alerts: trigger when `last > day_high * 1.002` for a symbol labeled WATCH.
- **FR-08.6** Invalidation alerts: trigger when `last < stop` for a symbol with an active open watch.

### FR-09 — Rate Limiting & Resilience

- **FR-09.1** Scanner SHALL implement token-bucket rate limiter at 3 req/s for Coinbase public API.
- **FR-09.2** On 429, scanner SHALL back off exponentially (base 2s, max 60s) and retry up to 3 times before marking the symbol as "stale".
- **FR-09.3** On network error, scanner SHALL log the error, skip the symbol, and continue the scan.
- **FR-09.4** Partial scan results SHALL be surfaced with a stale indicator rather than blocking the full scan.

### FR-10 — UI

- **FR-10.1** A single-page dashboard SHALL display a sortable, filterable market table.
- **FR-10.2** Columns: Symbol, Last Price, 24h %, Score, Label, Pos-in-Range (bar), Volume (USD), Ladder Zone.
- **FR-10.3** Clicking a row opens a detail drawer with: full score breakdown, ladder levels, fib levels, stop, targets.
- **FR-10.4** "Copy Ladder" button copies a formatted text block to clipboard (see §13 for format).
- **FR-10.5** Alert panel shows recent alerts (last 20) with timestamp, symbol, zone, price.
- **FR-10.6** "Scan Now" button triggers an on-demand full scan.
- **FR-10.7** Last scan timestamp and scan status (running / idle / error) prominently displayed.

### FR-11 — Configuration

- **FR-11.1** `.env` file controls: `DATABASE_URL`, `COINBASE_API_BASE`, `TZ`, `SCAN_INTERVAL_SECONDS`.
- **FR-11.2** `config/strategy.yaml` controls: `min_quote_volume`, label thresholds, scoring weights, stop %, quiet hours.
- **FR-11.3** Config changes in `strategy.yaml` take effect at **next scan run only**. Open watches are NOT reminted immediately — their ladder levels are frozen from the scan that opened them. Rationale: mid-watch reminting would confuse zone tracking. If a remint is needed, close the watch manually or wait for next scan to produce new ladders.

### FR-12 — Pinned Watches

- **FR-12.1** The user can pin any symbol (regardless of score or label) via the UI or `watchlist` API.
- **FR-12.2** Pinned symbols: (a) always get candle fetches, (b) always get ladder computation (unless CHASE/SKIP), (c) receive ZONE_A_ENTRY, ZONE_B_ENTRY, BREAKOUT_WATCH, and INVALIDATION alerts **regardless of composite score** (no score gate).
- **FR-12.3** Pinned status is stored permanently in `symbols.on_watchlist = 1`. It survives scanner restarts and process crashes.
- **FR-12.4** Pinned symbols always appear in the UI table at the top (pinned group) regardless of score/label filters.
- **FR-12.5** Breakout alert: `last > day_high * 1.002` for ≥1 scan while pinned → fires BREAKOUT_WATCH once (deduped 6h).
- **FR-12.6** Invalidation alert: `last < stop_price` for ≥1 scan while watch is active → fires INVALIDATION once. Fires for pinned symbols even if score < 70.

---

## 7. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Full scan of liquid Coinbase USD universe (≤200 pairs) completes in < 30s on a standard laptop |
| NFR-02 | Performance | UI table renders updated data within 3s of scan completion |
| NFR-03 | Reliability | Scanner worker process auto-restarts on crash via process supervisor |
| NFR-04 | Reliability | No alert is permanently lost — undelivered alerts must persist until delivered or TTL expiry |
| NFR-05 | Correctness | Scores are reproducible from stored snapshot data (same inputs → same output) |
| NFR-06 | Security | No private API keys are required, stored, or requested in v1 |
| NFR-07 | Storage | SQLite DB shall not exceed 500 MB under default retention policy (≤30d snapshots) |
| NFR-08 | Observability | All scan runs, alert events, and errors are structured-logged to `logs/tpt.jsonl` |
| NFR-09 | Portability | Must run on Windows 11 (primary), macOS, and Linux with `uv` or Docker |
| NFR-10 | Testability | Scorer and labeler are pure functions accepting feature dicts; unit tested with 90% coverage target |
| NFR-11 | Extensibility | Adding a new exchange requires implementing a single adapter interface; no core logic changes |
| NFR-12 | Latency | Alert delivery from zone detection to UI display ≤ 60s |

---

## 8. Domain Model & Glossary

| Term | Definition |
|---|---|
| **Symbol** | A Coinbase USD trading pair, e.g. `BTC-USD`. Identified by `product_id`. |
| **Snapshot** | A raw timestamped capture of market data for one symbol at one point in time. |
| **Feature** | A derived numeric value computed from snapshot data (pos_in_range, VWAP, RSI, etc.). |
| **Score** | A composite 0–100 value summarising setup quality. Higher = more attractive entry opportunity. |
| **Label** | A human-readable classification of scan quality for a symbol at scan time. Priority-ordered. |
| **Ladder** | A structured limit-order plan: Tranche A price, Tranche B price, stop, T1, T2. |
| **Tranche A** | Primary entry — 60% of intended position. Placed at 50–61.8% retrace or VWAP pocket. |
| **Tranche B** | Deeper discount entry — 40% of intended position. Placed at 78.6% retrace or swing shelf. |
| **Stop** | Hard exit level below Tranche B; structure invalidation. |
| **Target 1 (T1)** | First take-profit at or just below day high reclaim. |
| **Target 2 (T2)** | Extended take-profit at prior swing high or +5% extension. |
| **pos_in_range** | `(last - day_low) / (day_high - day_low)`; 0 = at day low, 1 = at day high. |
| **VWAP pocket** | Price band within ±0.5% of the 24h VWAP. Strong magnetic support/resistance zone. |
| **Fib retrace** | Standard Fibonacci retracement level from day impulse (day_low → day_high). |
| **Swing shelf** | Lowest daily pivot low in the past 7d; acts as structural support. |
| **Quiet hours** | Configurable time window (default 00:00–07:59 Nairobi) where alert delivery is suppressed. |
| **Dedupe window** | Duration after an alert fires during which a repeat is suppressed (default 6h). |
| **Chase rule** | Prohibition on entering when `day_change_pct > 15 AND pos_in_range > 0.80`. |
| **RS vs BTC** | Relative strength: `symbol_day_change_pct - BTC_USD_day_change_pct`. |
| **Stale symbol** | A symbol whose data could not be fetched in the current scan; marked with a stale indicator. |

---

## 9. Scoring & Labeling Specification

### 9.1 Label Priority Tree

Each symbol receives **exactly one primary label**. The evaluation is a strict decision tree — the first branch that matches wins. No blending.

```
Priority  Label        Condition
────────  ───────────  ─────────────────────────────────────────────────────
  1       SKIP         quote_vol_24h < MIN_QUOTE_VOLUME  (default $1M)
                       → exits pipeline; no score, no ladder, no alert
  2       CHASE        day_change_pct > chase_change_pct (15)
                         AND pos_in_range > chase_pos_threshold (0.80)
                       → no ladder; no entry alert; even if pinned
  3       ENTRY_ZONE   (|last - vwap_24h| / vwap_24h ≤ 0.005)
                         OR (fib_500 ≤ last ≤ fib_618)
                         AND composite_score ≥ entry_zone_score_min (60)
                         AND label is not already SKIP or CHASE
  4       COILED       coiled_change_low (-3) ≤ day_change_pct ≤ coiled_change_high (5)
                         AND coiled_pos_low (0.30) ≤ pos_in_range ≤ coiled_pos_high (0.65)
                         AND quote_vol_24h ≥ MIN_QUOTE_VOLUME
  5       EARLY        day_change_pct > early_change_min (2)
                         AND pos_in_range < early_pos_max (0.75)
                         AND not already CHASE
  6       WATCH        all remaining (score ≥ 50 implied; below this still WATCH but unlit)
  (n/a)   WATCH-dim    score < 50; shown greyed in table, no active zone highlight
```

**Secondary tags** (stored in `scores.tags`, shown in detail drawer):
- `VWAP_CONFLUENCE` — true if `|last - vwap_24h| / vwap_24h ≤ 0.005`, regardless of primary label
- `FIB50_TOUCH` — true if `|last - fib_500| / fib_500 ≤ 0.003`
- `FIB62_TOUCH` — true if `|last - fib_618| / fib_618 ≤ 0.003`
- `SWING_SHELF_NEAR` — true if `|last - swing_shelf_7d| / swing_shelf_7d ≤ 0.01`
- `OVERBOUGHT_1H` — true if `rsi_1h > 65`
- `PINNED` — true if symbol is on user watchlist

Example: HYPE is ENTRY_ZONE (primary) with tags `["VWAP_CONFLUENCE", "FIB50_TOUCH", "PINNED"]`.
Example: NEAR is WATCH (primary) with tags `["SWING_SHELF_NEAR", "PINNED"]` — no entry alert unless it drops into zone.

All thresholds are stored in `config/strategy.yaml` and reloaded at each scan.

### 9.2 Scoring Formula (v1 Heuristic)

**Composite score** — weighted sum, clamped to [0, 100]:

```
score = 50  (baseline)

# ── Positive contributors ──────────────────────────────────
+ LIQUIDITY_BONUS       if quote_vol_24h > $5M      → +10
+ LIQUIDITY_BONUS_MED   if quote_vol_24h > $2M      → +5  (mutually exclusive with above)

+ COILED_STRUCTURE      if COILED label conditions met → +15
+ VWAP_CONFLUENCE       if last within VWAP ±0.5%    → +10
+ FIB_CONFLUENCE        if last within 50–62% fib band → +8
+ SWING_SHELF_SUPPORT   if last within 1% of swing shelf → +7

+ RS_BTC_POSITIVE       if rs_btc > 0               → +5
+ RS_BTC_STRONG         if rs_btc > 3               → +10  (mutually exclusive with above)

+ LOW_POS_IN_RANGE      if pos_in_range < 0.40       → +5
+ MID_POS_IN_RANGE      if 0.40 ≤ pos_in_range ≤ 0.65 → +3

+ VOLUME_EXPANDING      if vol_24h > 7d avg vol (from candles) → +5

# ── Negative contributors (penalties) ─────────────────────
- OVERBOUGHT_RSI_1H     if 1h RSI > 75              → -15
- OVERBOUGHT_RSI_1H_MED if 1h RSI > 65              → -7  (mutually exclusive)

- HIGH_POS_IN_RANGE     if pos_in_range > 0.85       → -10
- VERY_HIGH_CHANGE      if day_change_pct > 20       → -15
- HIGH_CHANGE           if day_change_pct > 10       → -8  (mutually exclusive)

- LOW_VOLUME_PENALTY    if quote_vol_24h < $2M       → -5
```

**Stored breakdown example** (used in detail drawer and audit):

```json
{
  "baseline": 50,
  "components": {
    "LIQUIDITY_BONUS": 10,
    "COILED_STRUCTURE": 15,
    "VWAP_CONFLUENCE": 10,
    "OVERBOUGHT_RSI_1H": 0,
    "HIGH_POS_IN_RANGE": -10
  },
  "total": 75,
  "clamped": 75
}
```

### 9.3 Config Weights (strategy.yaml structure)

```yaml
scoring:
  baseline: 50
  components:
    LIQUIDITY_BONUS: { threshold_usd: 5_000_000, points: 10 }
    LIQUIDITY_BONUS_MED: { threshold_usd: 2_000_000, points: 5 }
    COILED_STRUCTURE: { points: 15 }
    VWAP_CONFLUENCE: { band_pct: 0.5, points: 10 }
    FIB_CONFLUENCE: { fib_low: 0.50, fib_high: 0.618, points: 8 }
    SWING_SHELF_SUPPORT: { within_pct: 1.0, points: 7 }
    RS_BTC_POSITIVE: { min_rs: 0, points: 5 }
    RS_BTC_STRONG: { min_rs: 3, points: 10 }
    OVERBOUGHT_RSI_1H: { threshold: 75, points: -15 }
    OVERBOUGHT_RSI_1H_MED: { threshold: 65, points: -7 }
    HIGH_POS_IN_RANGE: { threshold: 0.85, points: -10 }
    VERY_HIGH_CHANGE: { threshold_pct: 20, points: -15 }
    HIGH_CHANGE: { threshold_pct: 10, points: -8 }
    LOW_VOLUME_PENALTY: { threshold_usd: 2_000_000, points: -5 }
    VOLUME_EXPANDING: { points: 5 }
    LOW_POS_IN_RANGE: { threshold: 0.40, points: 5 }
    MID_POS_IN_RANGE: { low: 0.40, high: 0.65, points: 3 }

labeling:
  min_quote_volume: 1_000_000
  skip_vol_threshold: 1_000_000
  chase_change_pct: 15
  chase_pos_threshold: 0.80
  coiled_change_low: -3
  coiled_change_high: 5
  coiled_pos_low: 0.30
  coiled_pos_high: 0.65
  early_change_min: 2
  early_pos_max: 0.75
  entry_zone_score_min: 60

ladder:
  tranche_a_size_pct: 60
  tranche_b_size_pct: 40
  stop_pct: 3
  fib_a_low: 0.50
  fib_a_high: 0.618
  fib_b_level: 0.786
  target2_extension_pct: 5

alerts:
  dedupe_hours: 6
  quiet_hours_start: "00:00"
  quiet_hours_end: "07:59"
  timezone: "Africa/Nairobi"
  digest_time: "08:00"
```

---

## 10. Alerting & Dedupe Specification

### 10.1 Alert Trigger Conditions

| Alert Type | Condition | Priority |
|---|---|---|
| `ZONE_A_ENTRY` | `last` newly inside Tranche A band (±0.3% tolerance) | HIGH |
| `ZONE_B_ENTRY` | `last` newly inside Tranche B band (±0.3% tolerance) | HIGH |
| `ZONE_A_APPROACH` | `last` within 1% above Tranche A | MEDIUM |
| `BREAKOUT_WATCH` | `last > day_high * 1.002` for a WATCH-labeled symbol | MEDIUM |
| `INVALIDATION` | `last < stop` for a symbol with active ladder watch | HIGH |
| `DIGEST` | Batched undelivered alerts surfaced at quiet-hours end | INFO |

### 10.2 Dedupe Logic (Exact Rule)

```
dedupe_key = f"{symbol}:{alert_type}:{round(zone_price, 3)}"

─── On each scan, for a symbol with an alert candidate ───────────────────────

1. DEDUPE GATE
   last_alert = most recent delivered alert with same dedupe_key
   if last_alert exists AND (now_utc - last_alert.created_at) < DEDUPE_HOURS:
     → SUPPRESS (same zone, same type, within window)
   else:
     → continue to step 2

2. ZONE EXIT DETECTION (for active watches)
   active_watch = open watch for this symbol+zone
   if active_watch exists:
     exit_pct = (last - zone_price) / zone_price   # positive = above zone
     if exit_pct > EXIT_TOLERANCE (default 1.0%):
       watch.consecutive_exit_count += 1
     else:
       watch.consecutive_exit_count = 0  # reset counter if price dips back into zone

     if watch.consecutive_exit_count >= ZONE_EXIT_SNAPSHOTS (default 2):
       # Confirmed exit — close watch, reset dedupe clock
       close_watch(reason="PRICE_EXIT")
       active_watch = None
       # Next entry will be treated as fresh → no dedupe suppression

3. FIRE OR SUPPRESS
   if active_watch is None (no open watch) AND price is inside zone (±ENTRY_TOL=0.3%):
     open_watch()
     fire_alert()   # dedupe clock starts now
   elif active_watch is not None:
     → already watching, suppress repeated entry alert
   else:
     → price outside zone or gate failed, no alert

─── Config params (strategy.yaml) ─────────────────────────────────────────────
DEDUPE_HOURS: 6
EXIT_TOLERANCE: 0.01          (1.0% above zone price)
ZONE_EXIT_SNAPSHOTS: 2         (must trade ≥EXIT_TOL for 2 consecutive snapshots)
ENTRY_TOLERANCE: 0.003         (0.3% band around zone price counts as "inside")
```

**Real example (ZORA):**
- Scan 1 (09:14): price $0.00852, Zone A = $0.00850 → inside → ALERT fires, watch opened
- Scan 2 (09:29): price $0.00862 → 1.4% above zone → `exit_count = 1` (need 2 snapshots)
- Scan 3 (09:44): price $0.00865 → 1.8% above zone → `exit_count = 2` → watch CLOSED, dedupe clock reset
- Scan 4 (09:59): price $0.00851 → re-enters zone → **NEW ALERT FIRES** (clock was reset)

### 10.3 Alert Payload Schema

```json
{
  "alert_id": "uuid",
  "symbol": "ETH-USD",
  "alert_type": "ZONE_A_ENTRY",
  "scan_run_id": "uuid",
  "price_at_alert": 2340.15,
  "zone_price": 2335.00,
  "zone_tolerance_pct": 0.3,
  "label_at_alert": "COILED",
  "score_at_alert": 72,
  "ladder": {
    "tranche_a": 2335.00,
    "tranche_b": 2270.00,
    "stop": 2201.90,
    "target_1": 2498.00,
    "target_2": 2620.00
  },
  "created_at": "2026-09-05T06:34:12Z",
  "delivered_at": null,
  "suppressed": false,
  "dedupe_key": "ETH-USD:ZONE_A_ENTRY:2335.000"
}
```

### 10.4 Quiet Hours Enforcement

**Scans run 24/7 with zero interruption.** Quiet hours affect only alert *delivery* to the UI.

1. Alert is generated and persisted to DB with `delivered_at = NULL`.
2. Alert delivery worker checks: `now_nairobi ∈ [quiet_start, quiet_end)` (default 00:00–07:59).
3. If quiet → set `suppressed = 1`, leave `delivered_at = NULL`.
4. At `digest_time` (default 08:00 Nairobi): delivery worker collects all suppressed alerts with `delivered_at IS NULL` and fires them as a DIGEST bundle.
5. DIGEST bundle = one consolidated UI notification: "N alerts while you slept" with expandable list sorted by `created_at`.
6. After DIGEST delivery: set `delivered_at = now` on all bundled alerts.

### 10.5 Single-Process Execution Model

To avoid SQLite write-lock contention while enabling 24/7 scanning + live UI:

- **Single Python process (`tpt serve`):**
  - Runs FastAPI on port 8000 (serves UI and API requests).
  - Spawns an in-process `AsyncIOScheduler` (APScheduler) that triggers `run_scan()` every `SCAN_INTERVAL_SECONDS` (default 900s = 15m).
  - SQLite database is opened with `journal_mode=WAL` and `busy_timeout=5000ms`.
  - **Single writer guarantee:** Scanner runs inside the process event loop; API endpoints are read-only (except user watchlist additions, which use a short, dedicated connection).
  - WAL mode guarantees UI reads NEVER block during scanner writes.

---

## 11. Data Model

See `docs/DATA_MODEL.md` for full schema. Summary:

| Table | Purpose |
|---|---|
| `symbols` | Master list of tracked products |
| `scan_runs` | Audit log of each scan execution |
| `snapshots` | Raw market data captured per symbol per scan |
| `features` | Computed feature values per symbol per scan |
| `scores` | Score breakdown + composite per symbol per scan |
| `ladders` | Computed ladder levels per symbol per scan |
| `watches` | Active zone watches (open → closed lifecycle) |
| `alerts` | Alert instances with delivery state |
| `user_settings` | Key-value config overrides |

---

## 12. API Outline

All endpoints under `/api/v1`. Backend is FastAPI.

### Market / Scan

| Method | Path | Description |
|---|---|---|
| `GET` | `/markets` | List all symbols with latest score, label, price |
| `GET` | `/markets/{symbol}` | Detail for one symbol (features, score breakdown, ladder) |
| `POST` | `/scan/trigger` | Trigger an on-demand scan; returns `scan_run_id` |
| `GET` | `/scan/status` | Current scan run status (idle / running / error) |
| `GET` | `/scan/history` | List recent scan runs with timing and error info |

### Alerts

| Method | Path | Description |
|---|---|---|
| `GET` | `/alerts` | List recent alerts (paginated, filterable by symbol/type) |
| `GET` | `/alerts/pending` | Undelivered alerts (quiet-hours suppressed) |
| `PATCH` | `/alerts/{id}/dismiss` | Mark alert dismissed by user |

### Config

| Method | Path | Description |
|---|---|---|
| `GET` | `/config` | Current effective config (merged env + yaml + db overrides) |
| `PATCH` | `/config` | Update user_settings overrides (min volume, quiet hours, etc.) |

### Watchlist

| Method | Path | Description |
|---|---|---|
| `GET` | `/watchlist` | User-defined watchlist symbols |
| `POST` | `/watchlist` | Add symbol to watchlist |
| `DELETE` | `/watchlist/{symbol}` | Remove from watchlist |

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/health/db` | DB connectivity check |

---

## 13. UI Wireframe Description

### 13.1 Technology Recommendation: Next.js (TypeScript)

**Rationale:** Streamlit is faster to scaffold but has significant limitations for the desired UX — no persistent WebSocket state for real-time alerts, limited custom components, and poor mobile/responsive behaviour. Next.js with a small set of libraries (react-query for data fetching, shadcn/ui or similar for table/drawer components) gives a production-grade foundation that scales to v2 features (P&L tracking, multi-exchange) without a rewrite.

**Trade-off acknowledged:** Streamlit would be faster for a one-day prototype. If speed is prioritized over UI quality, Streamlit is a valid MVP choice. Decision point: M1 → M2 transition.

### 13.2 Screen: Dashboard (Main)

```
┌─────────────────────────────────────────────────────────────────────┐
│  🔷 Top Picker Terminal          [Nairobi 09:34]  [● Scan Now]      │
│  Last scan: 09:30 · 127 pairs · 3 candidates · ✅ OK               │
├──────────┬──────────────────────────────────────────────────────────┤
│  ALERTS  │  MARKET TABLE                                            │
│  ──────  │  Filter: [All ▾] [COILED] [EARLY] [ENTRY_ZONE]          │
│  ETH-USD │  Sort: Score ▾                                           │
│  ZONE_A  │                                                          │
│  09:28   │  Symbol  │ Last   │ 24h%  │ Score │ Label  │ PIR  │ Vol  │
│  ──────  │  ────────┼────────┼───────┼───────┼────────┼──────┼────  │
│  SOL-USD │  SOL-USD │ 142.3  │ +1.8% │  78   │ COILED │███░  │ $8M  │
│  ZONE_B  │  ETH-USD │ 2341   │ -0.4% │  72   │ ENTRY  │██░░  │$41M  │
│  08:52   │  AVAX-USD│ 28.14  │ +3.1% │  64   │ EARLY  │████░ │ $3M  │
│  ──────  │  BTC-USD │ 62480  │ +0.2% │  58   │ WATCH  │████░ │$180M │
│  [more]  │  DOGE-USD│ 0.122  │ +18%  │  20   │ CHASE  │████  │ $22M │
│          │  XRP-USD │ 0.481  │ +0.1% │  35   │ WATCH  │███░  │ $6M  │
└──────────┴──────────────────────────────────────────────────────────┘
```

**PIR bar:** 4-segment progress bar showing position-in-range. Colour-coded: green (< 0.40), yellow (0.40–0.75), red (> 0.75).

### 13.3 Screen: Detail Drawer (Right side panel, slides in on row click)

```
┌──────────────────────────────────────────────┐
│  SOL-USD · COILED · Score 78          [✕]   │
│  Last: $142.30  │  24h: +1.8%               │
│  ──────────────────────────────────────────  │
│  LADDER (copy to clipboard →)               │
│  ┌──────────────────────────────────────┐   │
│  │  Tranche A (60%): $138.50            │   │
│  │  Tranche B (40%): $132.10            │   │
│  │  Stop:            $128.14            │   │
│  │  Target 1:        $148.90 (+7.6%)    │   │
│  │  Target 2:        $158.40 (+14.4%)   │   │
│  └──────────────────────────────────────┘   │
│  [📋 Copy Ladder Text]                       │
│  ──────────────────────────────────────────  │
│  FEATURES                                   │
│  Pos-in-range:  0.42                        │
│  VWAP 24h:      $140.20                     │
│  RSI 1h:        48.3                        │
│  RS vs BTC:     +1.6%                       │
│  ──────────────────────────────────────────  │
│  SCORE BREAKDOWN                            │
│  Baseline:           50                     │
│  Coiled structure:  +15                     │
│  Liquidity bonus:   +10                     │
│  VWAP confluence:   +10                     │
│  Mid pos range:      +3                     │
│  ─────────────────────────                  │
│  Total:              78                     │
└──────────────────────────────────────────────┘
```

### 13.4 Copy Ladder Text Format

This is the **exact template** output by the "Copy Ladder" button. Fields are right-aligned to the price column.

```
── {SYMBOL} · {LABEL} · Score {SCORE} ── {DATE} {TIME} EAT ──
A  60%:  ${tranche_a}          ← fill bid here
B  40%:  ${tranche_b}          ← deeper discount
Stop:    ${stop}               ← hard invalidation
T1:      ${target_1}  (+{rr_a_t1:.1f}R)
T2:      ${target_2}  (+{rr_a_t2:.1f}R)  ← trim here
⚠ Chase: no add above ${target_1} without confirmed reclaim hold.
```

**Live ZORA example** (from real session, A-tag ~$0.00850):
```
── ZORA-USD · COILED · Score 71 ── 2026-09-05 09:14 EAT ──
A  60%:  $0.00846          ← fill bid here
B  40%:  $0.00790          ← deeper discount
Stop:    $0.00766          ← hard invalidation
T1:      $0.00991  (+1.9R)
T2:      $0.01140  (+3.6R)  ← trim here
⚠ Chase: no add above $0.00991 without confirmed reclaim hold.
```

**R-values** computed from Tranche A: `R = (T - A) / (A - Stop)`. Rationale: most size is in A tranche.

**Formatting rules** for the copy string:
- Prices ≤ $0.01: show 5 decimal places (`$0.00846`)
- Prices $0.01–$1.00: 4 decimal places (`$0.4812`)
- Prices $1–$100: 2 decimal places (`$28.14`)
- Prices > $100: 2 decimal places (`$142.30`)
- Timestamp always Nairobi (EAT = UTC+3)

### 13.5 Alert Notification (in-app toast + panel)

```
🔔 ETH-USD · ZONE A ENTRY
   Price $2,341 entered ladder A zone ($2,335 ±0.3%)
   Label: COILED · Score 72
   [View Ladder]  [Dismiss]
   09:34 EAT
```

---

## 14. Risks & Open Questions

### Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Coinbase API rate limiting stalls scan | Medium | High | Token-bucket, exponential backoff, partial results |
| R2 | Timezone bugs cause wrong alert delivery | Medium | Medium | All stored in UTC; tz-conversion only at display layer |
| R3 | SQLite WAL contention (API reads during scanner write) | Low | Low | WAL mode enabled; readers never block; single writer |
| R4 | Feature drift: scorer diverges from documented formula | Medium | Medium | Formula in `strategy.yaml`; regression fixtures in tests/ |
| R5 | Coinbase deprecating a public endpoint | Low | High | Abstract adapter; swap coinbase.py without core changes |
| R6 | Windows path/encoding issues with SQLite | Low | Low | Windows CI from day one |
| R7 | Zone exit misfire: volatile price dips briefly outside zone → resets dedupe | Medium | Medium | ZONE_EXIT_SNAPSHOTS=2 guard; log every exit event |

### Open Questions — Resolved

| ID | Question | Resolution |
|---|---|---|
| OQ-1 | Next.js vs Streamlit? | **Next.js** — confirmed (§13.1) |
| OQ-2 | RSI for all symbols or candidates only? | **Candidates + pinned + BTC only** (FR-03.7) |
| OQ-4 | USDT pairs? | **USD-only in v1** — filter `quote_currency != 'USD'` |
| OQ-5 | 7d 1h candles vs 300-candle limit? | **7d = 168 candles** — safely under limit. Fetch `limit=300`. |
| OQ-7 | Do scans stop at night? | **No. Scans run 24/7.** Only UI alert *delivery* is muted 00:00–07:59. |
| OQ-8 | Breakout/invalidation in M3 or post-v1? | **In M3 for pinned symbols** (FR-12.5, FR-12.6). |
| OQ-9 | Process model — single or multi-process? | **Single process (`tpt serve`)** using APScheduler + FastAPI + WAL. |
| OQ-10 | Config hot-reload — remint immediately or next scan? | **Next scan only.** Open watches maintain frozen levels. |

### Open Questions — Active

| ID | Question | Owner | Target |
|---|---|---|---|
| OQ-3 | Alert delivery beyond in-app: Telegram, OS notification, email? | Product | M3 |
| OQ-6 | Auto-update symbols table when Coinbase adds new pairs mid-run? | Engineering | M2 |

---

## 15. Milestones & Acceptance Criteria

### M0 — Scaffold (1–2 days)

**Goal:** Repo structure, config system, DB migrations, CI pipeline.

| AC | Criterion |
|---|---|
| AC-M0.1 | `uv run python -m tpt.cli --help` succeeds |
| AC-M0.2 | DB migrations create all tables with `make db-migrate` |
| AC-M0.3 | `.env.example` and `config/strategy.yaml` present with all documented fields |
| AC-M0.4 | `pytest tests/` passes with 0 failures (empty stubs) |
| AC-M0.5 | `make lint` passes (ruff + mypy) |

### M1 — Scanner CLI (3–5 days)

**Goal:** Working scanner that fetches, persists, and logs results to console.

| AC | Criterion |
|---|---|
| AC-M1.1 | `tpt scan` fetches all liquid Coinbase USD pairs and completes in < 30s |
| AC-M1.2 | All feature values computed and stored in `features` table |
| AC-M1.3 | Scores and labels stored in `scores` table |
| AC-M1.4 | Console output shows top 10 COILED/EARLY candidates with score |
| AC-M1.5 | Rate limiter verified: no 429 errors in a normal scan run |
| AC-M1.6 | `pytest tests/unit/test_scorer.py` passes with known-input regression cases |

### M2 — Ladders (2–3 days)

**Goal:** Ladder computation and persistence for candidates.

| AC | Criterion |
|---|---|
| AC-M2.1 | `ladders` table populated for all COILED/EARLY/ENTRY_ZONE symbols |
| AC-M2.2 | Tranche A and B prices mathematically verified against fib formula |
| AC-M2.3 | Stop and targets computed per FR-06 |
| AC-M2.4 | `tpt scan --output json` prints ladder for each candidate |
| AC-M2.5 | Chase rule enforced: no ladder generated if CHASE label |

### M3 — Alerts (3–4 days)

**Goal:** Alert engine with dedupe, quiet hours, pinned-watch alerts, breakout, and invalidation.

| AC | Criterion |
|---|---|
| AC-M3.1 | Alerts fire ≤ 60s after zone entry detected in scan |
| AC-M3.2 | Same dedupe_key does not re-fire within 6h in normal conditions |
| AC-M3.3 | Scans continue 24/7; alert delivery suppressed 00:00–07:59 Nairobi; digest fires at 08:00 |
| AC-M3.4 | Zone exit requires ≥2 consecutive snapshots outside zone (ZONE_EXIT_SNAPSHOTS=2) before dedupe reset (regression test with ZORA fixture) |
| AC-M3.5 | All alerts stored in `alerts` table with correct payload |
| AC-M3.6 | Pinned symbol (score < 70) receives ZONE_A_ENTRY alert; non-pinned sub-70 does NOT |
| AC-M3.7 | BREAKOUT_WATCH fires once per pinned symbol when `last > day_high * 1.002` |
| AC-M3.8 | INVALIDATION fires once per pinned symbol when `last < stop_price` |

### M4 — UI (4–6 days)

**Goal:** Browser-based dashboard with table, drawer, and alerts panel.

| AC | Criterion |
|---|---|
| AC-M4.1 | Dashboard loads in < 3s on localhost |
| AC-M4.2 | Scan Now button triggers scan and updates table without page reload |
| AC-M4.3 | Clicking a row opens detail drawer with ladder and score breakdown |
| AC-M4.4 | Copy Ladder Text button copies formatted text to clipboard |
| AC-M4.5 | Alert panel shows last 20 alerts with correct timestamps in Nairobi TZ |
| AC-M4.6 | Label filter and score sort work correctly |

---

*End of PRD v1.0*
