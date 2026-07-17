"""Persistent market store (SQLite).

Single source of truth for player data and prices. The async scheduler
(scheduler.py) trickles fresh data in per player; reprices read whatever is
here *now* — prices always reflect the last time step and update aperiodically
as collection lands.

Tables:
  players         raw season stats + the current price block per player
  daily_views     one row per (player, day) of Wikipedia attention
  price_snapshots sparse price history (written when a reprice moves a player)
  events          human-readable market happenings (movers) -> /api/feed
  meta            scheduler bookkeeping (last stats refresh, etc.)
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from .db import DB_PATH
from .pricing import PlayerInputs, PricedPlayer

_lock = threading.Lock()

STAT_COLS = [
    "gp", "min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov",
    "pf", "fgm", "fga", "ftm", "fta", "fg3m", "team_win_pct", "dd2", "td3",
    "plus_minus",
]

# raw ingest row key -> players column
ROW_TO_COL = {
    "GP": "gp", "MIN": "min", "PTS": "pts", "REB": "reb", "OREB": "oreb",
    "DREB": "dreb", "AST": "ast", "STL": "stl", "BLK": "blk", "TOV": "tov",
    "PF": "pf", "FGM": "fgm", "FGA": "fga", "FTM": "ftm", "FTA": "fta",
    "FG3M": "fg3m", "W_PCT": "team_win_pct", "DD2": "dd2", "TD3": "td3",
    "PLUS_MINUS": "plus_minus",
}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init() -> None:
    with _lock, _conn() as conn:
        conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS players (
                season TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                team_abbr TEXT NOT NULL,
                {", ".join(f"{c} REAL NOT NULL DEFAULT 0" for c in STAT_COLS)},
                stats_updated_at TEXT,
                views_updated_at TEXT,
                price REAL,
                composite REAL,
                perf_z REAL,
                pop_z REAL,
                team_z REAL,
                momentum_z REAL,
                game_score REAL,
                tier TEXT,
                wiki_views INTEGER,
                priced_at TEXT,
                snap_price REAL,
                snap_ts TEXT,
                PRIMARY KEY (season, player_id)
            );
            CREATE TABLE IF NOT EXISTS daily_views (
                season TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                views INTEGER NOT NULL,
                PRIMARY KEY (season, player_id, date)
            );
            CREATE TABLE IF NOT EXISTS price_snapshots (
                season TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                ts TEXT NOT NULL,
                price REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots
                ON price_snapshots (season, player_id, ts);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                season TEXT NOT NULL,
                ts TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                message TEXT NOT NULL,
                delta_pct REAL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS profiles (
                season TEXT NOT NULL,
                player_id INTEGER NOT NULL,
                json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (season, player_id)
            )"""
        )
        for migration in (
            "ALTER TABLE events ADD COLUMN url TEXT",
            "ALTER TABLE players ADD COLUMN awards TEXT",
            "ALTER TABLE players ADD COLUMN bbref_id TEXT",
        ):
            try:
                conn.execute(migration)
            except sqlite3.OperationalError:
                pass  # column already exists


# ---------------------------------------------------------------- writes

def _bump_data_version(conn: sqlite3.Connection) -> None:
    """Collectors call this (inside their transaction) whenever market inputs
    change; the reprice loop only runs when the version moved."""
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('data_version', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)"
    )


def upsert_player_stats(season: str, rows: list[dict]) -> None:
    """Raw ingest rows (UPPERCASE keys) -> players table."""
    now = _now()
    cols = ["season", "player_id", "name", "team_abbr", *STAT_COLS, "awards", "bbref_id", "stats_updated_at"]
    sql = (
        f"INSERT INTO players ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))}) "
        "ON CONFLICT(season, player_id) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in ["name", "team_abbr", *STAT_COLS, "awards", "bbref_id", "stats_updated_at"])
    )
    with _lock, _conn() as conn:
        conn.executemany(
            sql,
            [
                (
                    season,
                    int(r["PLAYER_ID"]),
                    r["PLAYER_NAME"],
                    r["TEAM_ABBREVIATION"],
                    *[float(r.get(k, 0) or 0) for k in ROW_TO_COL],
                    r.get("AWARDS", ""),
                    r.get("BBREF_ID", ""),
                    now,
                )
                for r in rows
            ],
        )
        _bump_data_version(conn)


def upsert_daily_views(season: str, player_id: int, series: dict[str, int]) -> None:
    with _lock, _conn() as conn:
        conn.executemany(
            "INSERT INTO daily_views (season, player_id, date, views) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(season, player_id, date) DO UPDATE SET views = excluded.views",
            [(season, player_id, d, v) for d, v in series.items()],
        )
        conn.execute(
            "UPDATE players SET views_updated_at = ? WHERE season = ? AND player_id = ?",
            (_now(), season, player_id),
        )
        if series:
            _bump_data_version(conn)


def set_prices(season: str, priced: list[PricedPlayer]) -> None:
    now = _now()
    with _lock, _conn() as conn:
        conn.executemany(
            """UPDATE players SET price=?, composite=?, perf_z=?, pop_z=?, team_z=?,
               momentum_z=?, game_score=?, tier=?, wiki_views=?, priced_at=?
               WHERE season=? AND player_id=?""",
            [
                (
                    p.price, p.composite, p.perf_z, p.pop_z, p.team_z,
                    p.momentum_z, p.game_score, p.tier, p.wiki_views, now,
                    season, p.player_id,
                )
                for p in priced
            ],
        )


def add_snapshots(season: str, prices: dict[int, float]) -> None:
    """Record these players' current prices as history points."""
    now = _now()
    with _lock, _conn() as conn:
        conn.executemany(
            "INSERT INTO price_snapshots (season, player_id, ts, price) VALUES (?, ?, ?, ?)",
            [(season, pid, now, price) for pid, price in prices.items()],
        )
        conn.executemany(
            "UPDATE players SET snap_price = ?, snap_ts = ? WHERE season = ? AND player_id = ?",
            [(price, now, season, pid) for pid, price in prices.items()],
        )


def add_event(
    season: str,
    player_id: int,
    name: str,
    type_: str,
    message: str,
    delta_pct: float | None = None,
    url: str | None = None,
) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO events (season, ts, player_id, name, type, message, delta_pct, url) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (season, _now(), player_id, name, type_, message, delta_pct, url),
        )


def mark_priority(season: str, player_ids: list[int]) -> None:
    """Jump these players to the front of the attention-trickle queue
    (NULL timestamps sort first in stalest_players)."""
    with _lock, _conn() as conn:
        conn.executemany(
            "UPDATE players SET views_updated_at = NULL WHERE season = ? AND player_id = ?",
            [(season, pid) for pid in player_ids],
        )


def prune_stale(season: str, before_iso: str) -> int:
    """Drop players a full stats refresh didn't touch (id churn orphans),
    plus their attention data."""
    with _lock, _conn() as conn:
        cur = conn.execute(
            "DELETE FROM players WHERE season = ? "
            "AND (stats_updated_at IS NULL OR stats_updated_at < ?)",
            (season, before_iso),
        )
        conn.execute(
            "DELETE FROM daily_views WHERE season = ? AND player_id NOT IN "
            "(SELECT player_id FROM players WHERE season = ?)",
            (season, season),
        )
        return cur.rowcount


def set_meta(key: str, value: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---------------------------------------------------------------- reads

def get_meta(key: str) -> str | None:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def player_count(season: str) -> int:
    with _lock, _conn() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM players WHERE season = ?", (season,)
        ).fetchone()["n"]


def get_players(season: str) -> list[dict]:
    with _lock, _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM players WHERE season = ?", (season,)
            )
        ]


def view_totals(season: str, days: int | None = None) -> dict[int, int]:
    """Pageview sums per player; trailing `days` window (vs the newest data
    point) when given, whole season otherwise."""
    with _lock, _conn() as conn:
        params: list = [season]
        where = "season = ?"
        if days is not None:
            row = conn.execute(
                "SELECT MAX(date) AS d FROM daily_views WHERE season = ?", (season,)
            ).fetchone()
            if row["d"]:
                from datetime import date, timedelta

                latest = date(int(row["d"][:4]), int(row["d"][4:6]), int(row["d"][6:8]))
                cutoff = (latest - timedelta(days=days)).strftime("%Y%m%d")
                where += " AND date > ?"
                params.append(cutoff)
        return {
            r["player_id"]: r["total"]
            for r in conn.execute(
                f"SELECT player_id, SUM(views) AS total FROM daily_views "
                f"WHERE {where} GROUP BY player_id",
                params,
            )
        }


def get_daily_views(season: str) -> dict[str, dict[str, int]]:
    """{player_id_str: {date: views}} — shape history.py expects."""
    out: dict[str, dict[str, int]] = {}
    with _lock, _conn() as conn:
        for r in conn.execute(
            "SELECT player_id, date, views FROM daily_views WHERE season = ?",
            (season,),
        ):
            out.setdefault(str(r["player_id"]), {})[r["date"]] = r["views"]
    return out


def player_inputs(season: str) -> list[PlayerInputs]:
    totals = view_totals(season)
    recent = view_totals(season, days=30)
    return [
        PlayerInputs(
            player_id=r["player_id"],
            name=r["name"],
            team_id=0,
            team_abbr=r["team_abbr"],
            games_played=int(r["gp"]),
            minutes=r["min"],
            points=r["pts"],
            rebounds=r["reb"],
            off_rebounds=r["oreb"],
            def_rebounds=r["dreb"],
            assists=r["ast"],
            steals=r["stl"],
            blocks=r["blk"],
            turnovers=r["tov"],
            fouls=r["pf"],
            fgm=r["fgm"],
            fga=r["fga"],
            ftm=r["ftm"],
            fta=r["fta"],
            fg3m=r["fg3m"],
            team_win_pct=r["team_win_pct"],
            double_doubles=int(r["dd2"]),
            triple_doubles=int(r["td3"]),
            plus_minus=r["plus_minus"],
            wiki_views=totals.get(r["player_id"]) or None,
            wiki_views_recent=recent.get(r["player_id"]) or None,
        )
        for r in get_players(season)
    ]


def price_map(season: str) -> dict[int, float]:
    with _lock, _conn() as conn:
        return {
            r["player_id"]: r["price"]
            for r in conn.execute(
                "SELECT player_id, price FROM players WHERE season = ? AND price IS NOT NULL",
                (season,),
            )
        }


def stalest_players(season: str, k: int) -> list[dict]:
    """Players whose attention data is oldest — next in the trickle queue."""
    with _lock, _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT player_id, name FROM players WHERE season = ? "
                "ORDER BY views_updated_at IS NOT NULL, views_updated_at LIMIT ?",
                (season, k),
            )
        ]


def get_profile(season: str, player_id: int) -> dict | None:
    import json as _json

    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT json FROM profiles WHERE season = ? AND player_id = ?",
            (season, player_id),
        ).fetchone()
        return _json.loads(row["json"]) if row else None


def set_profile(season: str, player_id: int, profile: dict) -> None:
    import json as _json

    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO profiles (season, player_id, json, fetched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(season, player_id) DO UPDATE SET json = excluded.json, fetched_at = excluded.fetched_at",
            (season, player_id, _json.dumps(profile), _now()),
        )


def stalest_profile(season: str) -> int | None:
    """Priced player whose scouting profile is oldest (or missing) — next in
    the slow career-aggregation queue."""
    with _lock, _conn() as conn:
        row = conn.execute(
            """SELECT p.player_id FROM players p
               LEFT JOIN profiles pr ON pr.season = p.season AND pr.player_id = p.player_id
               WHERE p.season = ? AND p.price IS NOT NULL
               ORDER BY pr.fetched_at IS NOT NULL, pr.fetched_at
               LIMIT 1""",
            (season,),
        ).fetchone()
        return row["player_id"] if row else None


def events_since(last_id: int, limit: int = 50) -> list[dict]:
    with _lock, _conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM events WHERE id > ? ORDER BY id DESC LIMIT ?",
                (last_id, limit),
            )
        ]
