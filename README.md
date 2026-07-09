# NBAStock

A stock market for NBA players. Every player has a share price computed from
real stats — performance, popularity, and team strength — and (soon) users
trade them with virtual currency: long, short, and player ETFs.

## How prices work (model v0)

```
composite = 0.50·performance + 0.22·popularity + 0.18·team + 0.10·momentum   (all z-scores)
price     = $30 · e^(0.85 · composite)
```

- **Performance** — Hollinger Game Score from per-game box stats
- **Popularity** — REAL attention data: each player's Wikipedia pageviews over
  the season (log-scaled, 65%) blended with on-court star power (35%).
  Refresh with `python -m app.popularity` (~1200 free Wikimedia API calls).
- **Team** — win% of the player's team
- **Momentum** — last-10-games form vs. season form (wired, awaiting per-game data source)

### Continuous market (v2 architecture)

SQLite is the single source of truth (`app/store.py`): player stats, daily
attention data, current prices, sparse price snapshots, and market events all
live in one DB next to the trading ledger. An async scheduler inside the API
process (`app/scheduler.py`) keeps it fresh — no batch-and-restart:

- **trickle** — refresh the stalest player's last-45-days attention, one
  small Wikimedia call at a time (whole league cycles ~1–2×/day)
- **stats** — Basketball-Reference refresh once a day (stale ids pruned)
- **news** — ESPN NBA headlines every 15 min into the events feed, tied to
  players via ESPN's roster ids when the article tags an athlete
- **signals** — pluggable event detectors (`app/signals.py`): trade/injury/
  signing language in headlines, per-player attention spikes vs their own
  baseline, and live games via ESPN's scoreboard. A firing signal jumps the
  named players to the front of the trickle queue, flips tempo to `live`
  for a window, and lands in the feed. New detectors (odds moves, Reddit
  velocity, direct social feeds) just implement `detect()` and register.
- **reprice** — event-driven, not wall-clock: collectors bump a
  `data_version`; the loop reprices only when inputs actually changed
  (a quiet offseason night = zero reprices). Repricing is always global —
  z-scores are relative — and costs ~10ms for 400 players.

Collection tempo scales with how alive the league is via `NBASTOCK_TEMPO`
(`live` for game windows, `normal`, `idle`); in-season, a schedule check
should flip `live` on automatically during games.

Prices are driven by the **trailing-30-day** attention window (season totals
remain for fame display), so the market genuinely moves with the news cycle.
Reprice moves ≥0.5% become events: `GET /api/feed` (recent) and
`GET /api/feed/stream` (SSE) serve them for a live feed UI.

Players need 15+ games and 12+ min/game to qualify. A league-average player is
$30; Jokić-tier is ~$300; deep bench is ~$11.

## Design

The UI language — tokens, the player-card anatomy, color lanes, motion and
chart rules — is documented in **[DESIGN.md](DESIGN.md)**.

## Stack

- `backend/` — Python + FastAPI. Ingests real 2025-26 stats from
  Basketball-Reference (stats.nba.com blocks many ISPs), caches locally,
  prices all ~400 qualified players, proxies NBA CDN headshots.
- `frontend/` — Next.js + TypeScript + Tailwind. Player-card market UI.

## Run it

Backend (port 8000):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.ingest        # one-time data fetch (2 requests)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Frontend (port 3000):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Roadmap

- [x] Pricing engine on real NBA data
- [x] Player card market UI (team-color duotone banners, cutout headshots,
      halftone texture, foil borders on S/A tiers)
- [x] Accounts + virtual cash ($10k), buy/sell/short, portfolio, leaderboard
- [x] Price history + card sparklines — the popularity component is
      recomputed per day from a trailing-30d attention window, so prices
      move daily even in the offseason (draft/free-agency news moves
      attention). `GET /api/players/{id}/history` serves 120 days.
- [ ] Player ETFs (team funds, rookie index)
- [x] Continuous DB-backed market: async per-player collectors +
      event-driven global reprice + events/SSE feed endpoints
- [x] Live feed UI on the market page: price moves + real ESPN headlines
      (player-linked when the article tags an athlete)
- [x] Event detection skeleton: plug-and-play detectors that sense trades/
      injuries/games/attention spikes and make the market react
- [ ] Sentiment signals: Reddit r/nba mentions (free API), X/Twitter (paid)
- [ ] Advanced stats: real PER/BPM/VORP/WS from Basketball-Reference's
      advanced page → 2K-style overall ratings on cards
- [x] Real popularity signal (Wikipedia pageviews; X/Twitter API is paid —
      revisit if funded)
- [ ] Highlights on player pages
