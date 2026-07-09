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

Daily price movement comes from the popularity term: each day's price uses a
trailing-30-day pageview window (`app/history.py`), anchored so the series
ends at the official price. Refresh cadence for a live market: run
`python -m app.ingest && python -m app.popularity` daily (cron), then restart
or hit `POST /api/refresh`.

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
- [x] Real popularity signal (Wikipedia pageviews; X/Twitter API is paid —
      revisit if funded)
- [ ] Highlights on player pages
