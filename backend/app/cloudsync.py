"""Cloud sync: publish the market database to MongoDB Atlas.

SQLite stays the fast local engine the market runs on; Atlas is the cloud
home — one rich document per player (stats, price block, factor breakdown,
scouting profile/career, attention history), plus recent events and a sync
manifest. A deployed backend (or anyone you share access with) can read the
whole market from Atlas without touching your laptop.

Connection: set MONGODB_URI in the environment, or put the connection
string in backend/.mongodb_uri (gitignored). Atlas free tier (M0) is
plenty — the full market is a few MB.

CLI:
    python -m app.cloudsync push     # upload everything now
    python -m app.cloudsync pull     # restore a fresh SQLite from Atlas
    python -m app.cloudsync status   # what's up there

The scheduler also auto-pushes every 30 days when a URI is configured —
the "update my players once a month" loop.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import ingest, store

DB_NAME = os.environ.get("MONGODB_DB", "nbastock")
URI_FILE = Path(__file__).parent.parent / ".mongodb_uri"


def _uri() -> str | None:
    uri = os.environ.get("MONGODB_URI")
    if uri:
        return uri.strip()
    if URI_FILE.exists():
        return URI_FILE.read_text().strip() or None
    return None


def _client():
    from pymongo import MongoClient

    uri = _uri()
    if not uri:
        raise RuntimeError(
            "No MongoDB connection configured. Set MONGODB_URI or put the "
            f"connection string in {URI_FILE}"
        )
    return MongoClient(uri, serverSelectionTimeoutMS=10_000)


def _player_documents(season: str) -> list[dict]:
    """One document per player: the full dossier."""
    daily = store.get_daily_views(season)
    docs = []
    for r in store.get_players(season):
        pid = r["player_id"]
        prof = store.get_profile(season, pid) or {}
        docs.append(
            {
                "_id": pid,
                "season": season,
                "name": r["name"],
                "team": r["team_abbr"],
                "age": r["age"],
                "stats": {k: r[k] for k in (
                    "gp", "min", "pts", "reb", "ast", "stl", "blk", "tov",
                    "fgm", "fga", "fg3m", "team_win_pct",
                )},
                "market": {
                    "price": r["price"],
                    "composite": r["composite"],
                    "tier": r["tier"],
                    "factors": json.loads(r["factors"]) if r["factors"] else {},
                    "priced_at": r["priced_at"],
                },
                "awards": r["awards"],
                "profile": {k: prof.get(k) for k in (
                    "bio", "nickname", "wiki_url", "ratings", "shot_zones", "career",
                ) if k in prof},
                "attention": {
                    "season_views": r["wiki_views"],
                    "daily": daily.get(str(pid), {}),
                },
                "updated_at": datetime.now(timezone.utc),
            }
        )
    return docs


def push(season: str = ingest.DEFAULT_SEASON) -> dict:
    client = _client()
    db = client[DB_NAME]

    docs = _player_documents(season)
    if docs:
        from pymongo import ReplaceOne

        db.players.bulk_write(
            [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
        )

    events = store.events_since(0, 500)
    if events:
        from pymongo import ReplaceOne

        db.events.bulk_write(
            [ReplaceOne({"_id": e["id"]}, {**e, "_id": e["id"]}, upsert=True)
             for e in events]
        )

    db.meta.replace_one(
        {"_id": "sync"},
        {
            "_id": "sync",
            "season": season,
            "players": len(docs),
            "events": len(events),
            "pushed_at": datetime.now(timezone.utc),
        },
        upsert=True,
    )
    client.close()
    return {"players": len(docs), "events": len(events)}


def pull(season: str = ingest.DEFAULT_SEASON) -> dict:
    """Restore a local store from Atlas (fresh machine / deployment boot)."""
    client = _client()
    db = client[DB_NAME]
    docs = list(db.players.find({"season": season}))
    client.close()
    if not docs:
        return {"players": 0}

    store.init()
    rows = []
    for d in docs:
        s = d.get("stats", {})
        rows.append({
            "PLAYER_ID": d["_id"], "PLAYER_NAME": d["name"],
            "TEAM_ABBREVIATION": d["team"], "AGE": d.get("age", 26),
            "GP": s.get("gp", 0), "MIN": s.get("min", 0), "PTS": s.get("pts", 0),
            "REB": s.get("reb", 0), "OREB": 0, "DREB": s.get("reb", 0),
            "AST": s.get("ast", 0), "STL": s.get("stl", 0), "BLK": s.get("blk", 0),
            "TOV": s.get("tov", 0), "PF": 0, "FGM": s.get("fgm", 0),
            "FGA": s.get("fga", 0), "FTM": 0, "FTA": 0, "FG3M": s.get("fg3m", 0),
            "W_PCT": s.get("team_win_pct", 0.5), "AWARDS": d.get("awards", ""),
        })
    store.upsert_player_stats(season, rows)
    for d in docs:
        series = d.get("attention", {}).get("daily") or {}
        if series:
            store.upsert_daily_views(season, d["_id"], series)
        prof = d.get("profile")
        if prof:
            store.set_profile(season, d["_id"], {"player_id": d["_id"], **prof})
    return {"players": len(docs)}


def status() -> dict:
    client = _client()
    db = client[DB_NAME]
    manifest = db.meta.find_one({"_id": "sync"}) or {}
    counts = {
        "players": db.players.estimated_document_count(),
        "events": db.events.estimated_document_count(),
    }
    client.close()
    return {**counts, "last_push": str(manifest.get("pushed_at", "never"))}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "push":
        print(push())
    elif cmd == "pull":
        print(pull())
    else:
        print(status())
