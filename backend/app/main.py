"""NBAStock API.

Serves priced players to the Next.js frontend. Prices come from the pricing
engine (pricing.py) applied to cached real NBA stats (ingest.py).

Run:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from dataclasses import asdict

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import db, history, ingest
from .pricing import price_players

app = FastAPI(title="NBAStock API", version="0.1.0")
db.init()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Headshots are proxied through this API: the NBA CDN resets HTTP/2
# connections from browsers on some ISPs, but server-side requests get
# through. Fetched once, cached on disk forever.
NBA_CDN_HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/{player_id}.png"
HEADSHOT_DIR = ingest.DATA_DIR / "headshots"
HEADSHOT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

_cache: dict = {}
_history_cache: dict = {}

SPARK_DAYS = 30


def _history(season: str) -> dict:
    if season not in _history_cache:
        _history_cache[season] = history.daily_prices(season)
    return _history_cache[season]


def _priced(season: str) -> list[dict]:
    """Price all players for a season, memoized per process."""
    if season not in _cache:
        inputs = ingest.player_inputs(season)
        priced = price_players(inputs)
        hist = _history(season)["prices"]
        for i, p in enumerate(priced):
            d = asdict(p)
            d["rank"] = i + 1
            d["headshot"] = f"/api/headshots/{p.player_id}.png"
            series = hist.get(p.player_id, [])[-SPARK_DAYS:]
            d["spark"] = series
            d["change_30d_pct"] = (
                round((series[-1] / series[0] - 1) * 100, 2)
                if len(series) >= 2 and series[0] > 0
                else 0.0
            )
            _cache.setdefault(season, []).append(d)
    return _cache[season]


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
    rows = _priced(season)
    if search:
        q = search.lower()
        rows = [r for r in rows if q in r["name"].lower()]
    if team:
        rows = [r for r in rows if r["team_abbr"].lower() == team.lower()]
    return {"season": season, "count": len(rows), "players": rows[:limit]}


@app.get("/api/players/{player_id}")
def player_detail(player_id: int, season: str = ingest.DEFAULT_SEASON) -> dict:
    for r in _priced(season):
        if r["player_id"] == player_id:
            return r
    raise HTTPException(status_code=404, detail="Player not found or not qualified")


def _price_map(season: str) -> dict[int, float]:
    return {r["player_id"]: r["price"] for r in _priced(season)}


def _player_map(season: str) -> dict[int, dict]:
    return {r["player_id"]: r for r in _priced(season)}


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
        result = db.portfolio(username, _price_map(season))
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")
    players = _player_map(season)
    for h in result["holdings"]:
        p = players.get(h["player_id"])
        if p:
            h.update(
                name=p["name"], team_abbr=p["team_abbr"], tier=p["tier"],
                headshot=p["headshot"],
            )
    return result


@app.post("/api/trade")
def execute_trade(body: TradeBody, season: str = ingest.DEFAULT_SEASON) -> dict:
    price = _price_map(season).get(body.player_id)
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
    return {"leaderboard": db.leaderboard(_price_map(season))}


@app.get("/api/players/{player_id}/history")
def player_history(player_id: int, season: str = ingest.DEFAULT_SEASON) -> dict:
    hist = _history(season)
    series = hist["prices"].get(player_id)
    if series is None:
        raise HTTPException(status_code=404, detail="No history for player")
    return {"player_id": player_id, "dates": hist["dates"], "prices": series}


@app.get("/api/headshots/{player_id}.png")
def headshot(player_id: int) -> Response:
    path = HEADSHOT_DIR / f"{player_id}.png"
    if not path.exists():
        r = requests.get(
            NBA_CDN_HEADSHOT.format(player_id=player_id),
            headers=HEADSHOT_HEADERS,
            timeout=15,
        )
        if r.status_code != 200 or not r.content:
            raise HTTPException(status_code=404, detail="No headshot")
        HEADSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return Response(
        path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/refresh")
def refresh_data(season: str = ingest.DEFAULT_SEASON) -> dict:
    data = ingest.refresh(season)
    _cache.pop(season, None)
    _history_cache.pop(season, None)
    return {"season": season, "players_fetched": len(data["players"])}
