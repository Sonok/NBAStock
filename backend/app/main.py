"""NBAStock API.

Serves the live market from the persistent store (store.py). Background
collectors and the periodic reprice loop (scheduler.py) run inside this
process — start uvicorn and the market keeps itself fresh; there is no
batch-and-restart step.

Run:  uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import db, history, ingest, market, scheduler, store

SPARK_DAYS = 30
PLAYERS_TTL = 15  # seconds; the store only changes on reprice anyway
HISTORY_TTL = 600


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    store.init()
    if await asyncio.to_thread(market.seed_if_empty):
        pass  # first boot: legacy JSON caches imported + initial reprice
    task = None
    if os.environ.get("NBASTOCK_SCHEDULER", "1") != "0":
        task = asyncio.create_task(scheduler.run())
    yield
    if task:
        task.cancel()


app = FastAPI(title="NBAStock API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Headshots are proxied through this API: the NBA CDN resets HTTP/2
# connections from browsers on some ISPs, but server-side requests get
# through. Fetched once, cached on disk forever. Players the NBA CDN doesn't
# know (fresh rookies, two-way contracts) fall back to ESPN's headshots,
# resolved by name via ESPN's public athlete index.
NBA_CDN_HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"
ESPN_HEADSHOT = "https://a.espncdn.com/i/headshots/nba/players/full/{espn_id}.png"
HEADSHOT_DIR = ingest.DATA_DIR / "headshots"
HEADSHOT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

_memo: dict[str, tuple[float, object]] = {}


def _ttl(key: str, ttl: float, build):
    hit = _memo.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    value = build()
    _memo[key] = (time.monotonic(), value)
    return value


def _history(season: str) -> dict:
    return _ttl(f"hist:{season}", HISTORY_TTL, lambda: history.daily_prices(season))


def _market_rows(season: str) -> list[dict]:
    """Priced players from the store, shaped for the frontend."""

    def build() -> list[dict]:
        rows = [r for r in store.get_players(season) if r["price"] is not None]
        rows.sort(key=lambda r: r["price"], reverse=True)
        hist = _history(season)["prices"]
        out = []
        for i, r in enumerate(rows):
            series = hist.get(r["player_id"], [])[-SPARK_DAYS:]
            out.append(
                {
                    "player_id": r["player_id"],
                    "name": r["name"],
                    "team_id": 0,
                    "team_abbr": r["team_abbr"],
                    "price": r["price"],
                    "composite": r["composite"],
                    "perf_z": r["perf_z"],
                    "pop_z": r["pop_z"],
                    "team_z": r["team_z"],
                    "momentum_z": r["momentum_z"],
                    "game_score": r["game_score"],
                    "tier": r["tier"],
                    "wiki_views": r["wiki_views"],
                    "rank": i + 1,
                    "headshot": f"/api/headshots/{r['player_id']}.png",
                    "spark": series,
                    "change_30d_pct": (
                        round((series[-1] / series[0] - 1) * 100, 2)
                        if len(series) >= 2 and series[0] > 0
                        else 0.0
                    ),
                    "stats": {
                        "gp": int(r["gp"]),
                        "min": r["min"],
                        "pts": r["pts"],
                        "reb": r["reb"],
                        "ast": r["ast"],
                        "stl": r["stl"],
                        "blk": r["blk"],
                        "team_win_pct": r["team_win_pct"],
                    },
                }
            )
        return out

    return _ttl(f"players:{season}", PLAYERS_TTL, build)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/players")
def players(
    season: str = ingest.DEFAULT_SEASON,
    limit: int = 60,
    search: str = "",
    team: str = "",
) -> dict:
    rows = _market_rows(season)
    if search:
        q = search.lower()
        rows = [r for r in rows if q in r["name"].lower()]
    if team:
        rows = [r for r in rows if r["team_abbr"].lower() == team.lower()]
    return {"season": season, "count": len(rows), "players": rows[:limit]}


@app.get("/api/players/{player_id}/history")
def player_history(player_id: int, season: str = ingest.DEFAULT_SEASON) -> dict:
    hist = _history(season)
    series = hist["prices"].get(player_id)
    if series is None:
        raise HTTPException(status_code=404, detail="No history for player")
    return {"player_id": player_id, "dates": hist["dates"], "prices": series}


@app.get("/api/players/{player_id}")
def player_detail(player_id: int, season: str = ingest.DEFAULT_SEASON) -> dict:
    for r in _market_rows(season):
        if r["player_id"] == player_id:
            return r
    raise HTTPException(status_code=404, detail="Player not found or not qualified")


class UserBody(BaseModel):
    username: str


class TradeBody(BaseModel):
    username: str
    player_id: int
    shares: float
    action: str  # "buy" | "sell"


@app.post("/api/users")
def create_user(body: UserBody) -> dict:
    try:
        user = db.get_or_create_user(body.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"username": user["username"], "cash": user["cash"]}


@app.get("/api/users/{username}/portfolio")
def get_portfolio(username: str, season: str = ingest.DEFAULT_SEASON) -> dict:
    try:
        result = db.portfolio(username, store.price_map(season))
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")
    players_by_id = {r["player_id"]: r for r in _market_rows(season)}
    for h in result["holdings"]:
        p = players_by_id.get(h["player_id"])
        if p:
            h.update(
                name=p["name"], team_abbr=p["team_abbr"], tier=p["tier"],
                headshot=p["headshot"],
            )
    return result


@app.post("/api/trade")
def execute_trade(body: TradeBody, season: str = ingest.DEFAULT_SEASON) -> dict:
    price = store.price_map(season).get(body.player_id)
    if price is None:
        raise HTTPException(status_code=404, detail="Player not found or not qualified")
    try:
        return db.trade(body.username, body.player_id, body.shares, body.action, price)
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/leaderboard")
def get_leaderboard(season: str = ingest.DEFAULT_SEASON) -> dict:
    return {"leaderboard": db.leaderboard(store.price_map(season))}


@app.get("/api/feed")
def feed(since_id: int = 0, limit: int = 50) -> dict:
    return {"events": store.events_since(since_id, limit)}


@app.get("/api/feed/stream")
async def feed_stream(since_id: int = 0) -> StreamingResponse:
    """Server-sent events: one message per new market event."""

    async def gen():
        last = since_id
        while True:
            events = await asyncio.to_thread(store.events_since, last, 50)
            for e in reversed(events):
                last = max(last, e["id"])
                yield f"data: {json.dumps(e)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _fetch_headshot(player_id: int) -> bytes | None:
    r = requests.get(
        NBA_CDN_HEADSHOT.format(player_id=player_id),
        headers=HEADSHOT_HEADERS,
        timeout=15,
    )
    if r.status_code == 200 and r.content:
        return r.content
    player = next(
        (p for p in store.get_players(ingest.DEFAULT_SEASON) if p["player_id"] == player_id),
        None,
    )
    if not player:
        return None
    espn_id = ingest.espn_id_index().get(ingest._normalize_name(player["name"]))
    if not espn_id:
        return None
    r = requests.get(
        ESPN_HEADSHOT.format(espn_id=espn_id), headers=HEADSHOT_HEADERS, timeout=15
    )
    if r.status_code == 200 and r.content:
        return r.content
    return None


@app.get("/api/headshots/{player_id}.png")
def headshot(player_id: int) -> Response:
    path = HEADSHOT_DIR / f"{player_id}.png"
    if not path.exists():
        content = _fetch_headshot(player_id)
        if content is None:
            raise HTTPException(status_code=404, detail="No headshot")
        HEADSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return Response(
        path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
