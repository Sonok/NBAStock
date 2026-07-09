"""Async background collectors + the periodic reprice loop.

Runs inside the FastAPI process (started from the app's lifespan). Three
independent loops, all writing to the store:

  trickle   every TRICKLE_SECONDS, refresh the stalest player's attention
            data (one small Wikimedia call — the whole league cycles ~1-2x
            a day without ever bursting)
  stats     Basketball-Reference season stats, once per STATS_HOURS
  reprice   every REPRICE_SECONDS, recompute all prices from whatever data
            has landed since the last time step; movers become events

Disable with NBASTOCK_SCHEDULER=0 (tests, one-off scripts).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import requests

from . import ingest, market, popularity, store

log = logging.getLogger("nbastock.scheduler")

TRICKLE_SECONDS = 90
REPRICE_SECONDS = 300
STATS_HOURS = 24
SEASON = ingest.DEFAULT_SEASON


def _hours_since(iso: str | None) -> float:
    if not iso:
        return float("inf")
    then = datetime.fromisoformat(iso)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


async def _trickle_loop() -> None:
    session = requests.Session()
    while True:
        try:
            stale = await asyncio.to_thread(store.stalest_players, SEASON, 1)
            if stale:
                p = stale[0]
                days = await asyncio.to_thread(
                    popularity.update_player_views,
                    session, SEASON, p["player_id"], p["name"],
                )
                log.info("trickle: %s (%d days)", p["name"], days)
        except Exception:
            log.exception("trickle failed")
        await asyncio.sleep(TRICKLE_SECONDS)


async def _stats_loop() -> None:
    while True:
        try:
            if _hours_since(store.get_meta("last_stats_refresh")) >= STATS_HOURS:
                batch_start = datetime.now(timezone.utc).isoformat()
                data = await asyncio.to_thread(ingest.refresh, SEASON)
                await asyncio.to_thread(
                    store.upsert_player_stats, SEASON, data["players"]
                )
                pruned = await asyncio.to_thread(
                    store.prune_stale, SEASON, batch_start
                )
                store.set_meta("last_stats_refresh", batch_start)
                log.info(
                    "stats refreshed: %d players (%d stale pruned)",
                    len(data["players"]), pruned,
                )
        except Exception:
            log.exception("stats refresh failed")
        await asyncio.sleep(3600)


async def _reprice_loop() -> None:
    while True:
        await asyncio.sleep(REPRICE_SECONDS)
        try:
            summary = await asyncio.to_thread(market.reprice, SEASON)
            if summary.get("events") or summary.get("snapshots"):
                log.info("reprice: %s", summary)
        except Exception:
            log.exception("reprice failed")


async def run() -> None:
    await asyncio.gather(_trickle_loop(), _stats_loop(), _reprice_loop())
