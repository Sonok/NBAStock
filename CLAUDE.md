# NBAStock — working notes for Claude

Player stock market for NBA players. Python FastAPI + SQLite backend
(`backend/`), Next.js 14 frontend (`frontend/`). Model docs in MODEL.md,
design system in DESIGN.md. End goal: pitch at the Mokhtarzada Hatchery
(UMD). Virtual currency only — no real money.

## Agenda (current)

1. **Finish MongoDB Atlas hookup** (in progress — waiting on Sonok):
   - Sign up via GitHub Student Pack: https://education.github.com/pack →
     MongoDB offer ($50 Atlas credit; the M0 cluster itself is free).
   - Create an M0 cluster, a database user, and allow network access from
     `0.0.0.0/0`.
   - Put the connection string in the gitignored secret file:
     `echo 'mongodb+srv://...' > backend/.mongodb_uri`
     (never commit this — it's under `# Secrets` in .gitignore).
   - First push: `cd backend && .venv/bin/python -m app.cloudsync push`,
     then `... status` to verify (~580 player docs). The scheduler
     auto-pushes every 30 days after that.

2. **Client-side hosting** (next up): deploy the Next.js frontend so the
   app is reachable off-laptop. Student Pack helps here too — Namecheap
   free domain, DigitalOcean/Azure credits; Vercel free tier is the easy
   path for the frontend. Backend deployment can follow (it can boot from
   Atlas via `cloudsync pull`).

## Backlog

- Sentiment collectors for the `SentimentProvider` ABC — Reddit r/nba
  (free, needs OAuth app), Bluesky firehose (free), Claude scoring;
  X/Twitter last (pay-per-read, gate behind signals).
- Player ETFs (basket instruments).
- Intraday live-game pricing; in-season MatchupFactor.
- Advanced stats from bbref advanced page (PER/BPM/VORP).
- Highlights on player pages.
- Optional: reset the legacy `sonok` account password (claimed with a
  test password during auth testing).

## Hard rules

- **Feed is news, not numbers** — no numeric price-move entries in the
  feed, ever (user said this twice). `/api/feed` filters
  `type='price_move'`.
- stats.nba.com and cdn.nba.com are blocked on this network — use
  Basketball-Reference/Wikipedia/ESPN, and the server-side headshot proxy.
- Run backend commands from `backend/` with `.venv/bin/python` /
  `.venv/bin/uvicorn` (absolute or cd first).
