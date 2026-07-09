"""NBAStock trading ledger (SQLite).

MVP market rules:
- Every new user starts with $10,000 virtual cash.
- Positions are per (user, player); negative shares = a short position.
- Buys need cash; sells past zero open a short. Short exposure is capped at
  1x equity so accounts can't blow up to negative net worth on a whim.
- avg_cost tracks the entry basis while a position grows; crossing zero
  (long -> short or back) resets the basis at the crossing trade's price.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "nbastock.db"
STARTING_CASH = 10_000.0

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _lock, _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                cash REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS positions (
                user_id INTEGER NOT NULL REFERENCES users(id),
                player_id INTEGER NOT NULL,
                shares REAL NOT NULL,
                avg_cost REAL NOT NULL,
                PRIMARY KEY (user_id, player_id)
            );
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                player_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                shares REAL NOT NULL,
                price REAL NOT NULL,
                ts TEXT NOT NULL
            );
            """
        )


def get_or_create_user(username: str) -> dict:
    username = username.strip().lower()
    if not (3 <= len(username) <= 20) or not username.replace("_", "").isalnum():
        raise ValueError("Username must be 3-20 letters, numbers, or underscores")
    with _lock, _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (username, cash, created_at) VALUES (?, ?, ?)",
                (username, STARTING_CASH, datetime.now(timezone.utc).isoformat()),
            )
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row)


def _positions(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT player_id, shares, avg_cost FROM positions WHERE user_id = ? AND shares != 0",
            (user_id,),
        )
    ]


def portfolio(username: str, prices: dict[int, float]) -> dict:
    """Positions marked to market. `prices` maps player_id -> current price."""
    with _lock, _conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
        if user is None:
            raise KeyError(username)
        positions = _positions(conn, user["id"])

    holdings = []
    market_value = 0.0
    for pos in positions:
        price = prices.get(pos["player_id"], 0.0)
        value = pos["shares"] * price
        market_value += value
        holdings.append(
            {
                **pos,
                "price": price,
                "market_value": round(value, 2),
                "unrealized_pl": round((price - pos["avg_cost"]) * pos["shares"], 2),
            }
        )
    equity = user["cash"] + market_value
    return {
        "username": user["username"],
        "cash": round(user["cash"], 2),
        "market_value": round(market_value, 2),
        "equity": round(equity, 2),
        "total_return_pct": round((equity / STARTING_CASH - 1) * 100, 2),
        "holdings": holdings,
    }


def trade(username: str, player_id: int, shares: float, action: str, price: float) -> dict:
    """Execute a buy or sell at `price`. Returns the updated cash + position."""
    if action not in ("buy", "sell"):
        raise ValueError("action must be 'buy' or 'sell'")
    if shares <= 0 or shares != round(shares, 4):
        raise ValueError("shares must be positive")

    signed = shares if action == "buy" else -shares
    with _lock, _conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
        if user is None:
            raise KeyError(username)

        pos = conn.execute(
            "SELECT shares, avg_cost FROM positions WHERE user_id = ? AND player_id = ?",
            (user["id"], player_id),
        ).fetchone()
        old_shares = pos["shares"] if pos else 0.0
        old_avg = pos["avg_cost"] if pos else 0.0
        new_shares = old_shares + signed
        new_cash = user["cash"] - signed * price

        if action == "buy" and new_cash < 0:
            raise ValueError(f"Not enough cash: need ${signed * price:,.2f}, have ${user['cash']:,.2f}")

        # Margin rule: total short exposure (this trade included) <= equity.
        if new_shares < 0:
            others = [
                p for p in _positions(conn, user["id"]) if p["player_id"] != player_id
            ]
            short_exposure = abs(new_shares) * price + sum(
                abs(p["shares"]) * p["avg_cost"] for p in others if p["shares"] < 0
            )
            long_value = sum(
                p["shares"] * p["avg_cost"] for p in others if p["shares"] > 0
            )
            equity = new_cash + long_value - abs(new_shares) * price
            if short_exposure > max(equity, 0):
                raise ValueError("Short exposure would exceed your equity (1x margin limit)")

        # Basis: grows with same-direction adds, resets when crossing zero.
        if old_shares == 0 or (old_shares > 0) != (new_shares > 0):
            new_avg = price
        elif abs(new_shares) > abs(old_shares):
            new_avg = (abs(old_shares) * old_avg + shares * price) / abs(new_shares)
        else:
            new_avg = old_avg

        conn.execute(
            """INSERT INTO positions (user_id, player_id, shares, avg_cost)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id, player_id)
               DO UPDATE SET shares = excluded.shares, avg_cost = excluded.avg_cost""",
            (user["id"], player_id, new_shares, new_avg),
        )
        conn.execute("UPDATE users SET cash = ? WHERE id = ?", (new_cash, user["id"]))
        conn.execute(
            "INSERT INTO trades (user_id, player_id, action, shares, price, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], player_id, action, shares, price, datetime.now(timezone.utc).isoformat()),
        )
        return {
            "cash": round(new_cash, 2),
            "player_id": player_id,
            "shares": new_shares,
            "avg_cost": round(new_avg, 2),
            "executed_price": price,
        }


def leaderboard(prices: dict[int, float]) -> list[dict]:
    with _lock, _conn() as conn:
        users = conn.execute("SELECT * FROM users").fetchall()
        rows = []
        for user in users:
            market_value = sum(
                p["shares"] * prices.get(p["player_id"], 0.0)
                for p in _positions(conn, user["id"])
            )
            equity = user["cash"] + market_value
            rows.append(
                {
                    "username": user["username"],
                    "equity": round(equity, 2),
                    "total_return_pct": round((equity / STARTING_CASH - 1) * 100, 2),
                }
            )
    rows.sort(key=lambda r: r["equity"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows
