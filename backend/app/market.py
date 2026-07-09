"""Market operations: reprice, snapshot, seed.

Repricing is the periodic global step the async collectors feed into:
read whatever data is in the store right now, run the pricing model over
the whole league (z-scores are relative, so everyone reprices together —
~10ms for 400 players), write prices back, and record movers as events
and snapshots. Between reprices, the market simply holds the last prices.
"""

from __future__ import annotations

import json

from . import ingest, popularity, store
from .pricing import price_players

EVENT_MOVE_PCT = 0.5      # a reprice move this big becomes a feed event
SNAPSHOT_MOVE_PCT = 0.25  # ...this big becomes a price-history point


def reprice(season: str = ingest.DEFAULT_SEASON) -> dict:
    inputs = store.player_inputs(season)
    priced = price_players(inputs)
    if not priced:
        return {"priced": 0}

    old = store.price_map(season)
    store.set_prices(season, priced)

    snapshots: dict[int, float] = {}
    events = 0
    prev_snap = {
        r["player_id"]: r["snap_price"]
        for r in store.get_players(season)
        if r["snap_price"] is not None
    }
    for p in priced:
        before = old.get(p.player_id)
        if before is None:
            snapshots[p.player_id] = p.price  # first pricing: seed history
            continue
        delta_pct = (p.price / before - 1) * 100 if before else 0.0
        snap_base = prev_snap.get(p.player_id, before)
        if snap_base and abs(p.price / snap_base - 1) * 100 >= SNAPSHOT_MOVE_PCT:
            snapshots[p.player_id] = p.price
        if abs(delta_pct) >= EVENT_MOVE_PCT:
            arrow = "▲" if delta_pct > 0 else "▼"
            store.add_event(
                season,
                p.player_id,
                p.name,
                "price_move",
                f"{p.name} {arrow} {abs(delta_pct):.1f}% to ${p.price:,.2f}",
                round(delta_pct, 2),
            )
            events += 1

    if snapshots:
        store.add_snapshots(season, snapshots)
    return {"priced": len(priced), "events": events, "snapshots": len(snapshots)}


def seed_if_empty(season: str = ingest.DEFAULT_SEASON) -> bool:
    """One-time migration: import the legacy JSON caches into the store."""
    if store.player_count(season) > 0:
        return False
    players_file = ingest.cache_path(season)
    if not players_file.exists():
        return False
    data = json.loads(players_file.read_text())
    store.upsert_player_stats(season, data["players"])
    for pid, series in popularity.load_daily(season).items():
        if series:
            store.upsert_daily_views(season, int(pid), series)
    reprice(season)
    return True
