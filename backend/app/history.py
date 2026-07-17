"""Daily price series per player.

The performance/team components move on game nights, but the popularity
component moves every single day — Wikipedia attention swings with games,
trades, injuries, and rumors, even in the offseason. So the daily price
series recomputes the model with popularity measured as an exponentially
decayed attention stock on each day, holding performance/team at season
level.

Each player's series is then anchored (scaled) so its final point equals the
official market price from pricing.price_players — one price rules trading,
and history shows how the market drifted into it.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from . import ingest, popularity
from .pricing import (
    BASE_PRICE,
    MAX_PRICE,
    MIN_PRICE,
    SPREAD,
    W_PERF,
    W_POP,
    W_TEAM,
    _zscores,
    game_score,
    price_players,
    qualifies,
    star_power,
)

HISTORY_DAYS = 120  # how far back the served series goes


def _date_range(start: str, end: str) -> list[str]:
    d0 = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    d1 = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    out = []
    while d0 <= d1:
        out.append(d0.strftime("%Y%m%d"))
        d0 += timedelta(days=1)
    return out


def daily_prices(season: str = ingest.DEFAULT_SEASON) -> dict:
    """{'dates': [...], 'prices': {player_id: [...]}} for the last HISTORY_DAYS."""
    from . import store

    inputs = store.player_inputs(season)
    daily = store.get_daily_views(season)
    pool = [p for p in inputs if qualifies(p)]
    if not pool or not daily:
        return {"dates": [], "prices": {}}

    start, end = popularity._season_window(season)
    all_dates = _date_range(start, end)
    # Serve only days that have already happened (offseason: series keeps
    # extending as new pageview days land).
    last_with_data = max(
        (max(s) for s in daily.values() if s), default=all_dates[-1]
    )
    all_dates = [d for d in all_dates if d <= last_with_data]
    out_dates = all_dates[-HISTORY_DAYS:]

    # Exponentially-decayed attention per player per day — the same model
    # that drives the live price (S_t = S_(t-1) * lambda + views_t).
    lam = 0.5 ** (1.0 / popularity.DECAY_HALF_LIFE_DAYS)
    decayed: list[list[float] | None] = []
    for p in pool:
        series = daily.get(str(p.player_id))
        if not series:
            decayed.append(None)
            continue
        vals: list[float] = []
        s_val = 0.0
        for d in all_dates:
            s_val = s_val * lam + series.get(d, 0)
            vals.append(s_val)
        decayed.append(vals)

    # Static components (move on game nights, which we don't have per-day).
    perf_z = _zscores([game_score(p) for p in pool])
    star_z = _zscores([star_power(p) for p in pool])
    team_z = _zscores([p.team_win_pct for p in pool])

    prices: dict[int, list[float]] = {p.player_id: [] for p in pool}
    date_index = {d: i for i, d in enumerate(all_dates)}
    for d in out_dates:
        i = date_index[d]
        att = [dec[i] if dec is not None else None for dec in decayed]
        known = sorted(t for t in att if t)
        median = known[len(known) // 2] if known else 0
        wiki_z = _zscores(
            [math.log10((t if t else median) + 1) for t in att]
        )
        for k, p in enumerate(pool):
            pop_z = 0.65 * wiki_z[k] + 0.35 * star_z[k]
            composite = W_PERF * perf_z[k] + W_POP * pop_z + W_TEAM * team_z[k]
            price = BASE_PRICE * math.exp(SPREAD * composite)
            prices[p.player_id].append(max(MIN_PRICE, min(MAX_PRICE, price)))

    # Anchor: scale each series so its last point equals the live market
    # price in the store (falling back to a fresh model run pre-seed).
    official = store.price_map(season) or {
        pp.player_id: pp.price for pp in price_players(inputs)
    }
    for pid, series in prices.items():
        target = official.get(pid)
        if target and series and series[-1] > 0:
            factor = target / series[-1]
            prices[pid] = [round(v * factor, 2) for v in series]

    return {"dates": out_dates, "prices": prices}
