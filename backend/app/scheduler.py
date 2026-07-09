"""Async background collectors + the adaptive reprice loop.

Runs inside the FastAPI process (started from the app's lifespan). Four
independent loops, all writing to the store:

  trickle   refresh the stalest player's attention data, one small
            Wikimedia call at a time
  stats     Basketball-Reference season stats, once per STATS_HOURS
  news      ESPN NBA headlines into the events feed
  reprice   EVENT-DRIVEN, not wall-clock: collectors bump a data_version
            in the store; this loop polls the version and only reprices
            when inputs actually changed. A quiet offseason night produces
            zero reprices; a burst of collection reprices within seconds.

Tempo scales collection to how alive the league is (NBASTOCK_TEMPO):
  live    in-game cadence — trickle every 20s, reprice check every 15s
          (in-season, a schedule check should flip this on during game
          windows; offseason it's manual/demo)
  normal  default day cadence
  idle    quiet cadence for overnight / deep offseason

Disable everything with NBASTOCK_SCHEDULER=0 (tests, one-off scripts).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import requests

from . import ingest, market, news, popularity, store

log = logging.getLogger("nbastock.scheduler")

TEMPOS = {
    "live": {"trickle": 20, "reprice_poll": 15},
    "normal": {"trickle": 90, "reprice_poll": 60},
    "idle": {"trickle": 600, "reprice_poll": 300},
}
TEMPO = TEMPOS.get(os.environ.get("NBASTOCK_TEMPO", "normal"), TEMPOS["normal"])
STATS_HOURS = 24
NEWS_SECONDS = 900
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
        await asyncio.sleep(TEMPO["trickle"])


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


async def _news_loop() -> None:
    while True:
        try:
            added = await asyncio.to_thread(news.collect, SEASON)
            if added:
                log.info("news: %d new headlines", added)
        except Exception:
            log.exception("news collection failed")
        await asyncio.sleep(NEWS_SECONDS)


async def _reprice_loop() -> None:
    last_version = store.get_meta("data_version")
    while True:
        await asyncio.sleep(TEMPO["reprice_poll"])
        try:
            version = store.get_meta("data_version")
            if version == last_version:
                continue  # nothing changed since the last time step
            summary = await asyncio.to_thread(market.reprice, SEASON)
            last_version = version
            log.info("reprice (data v%s): %s", version, summary)
        except Exception:
            log.exception("reprice failed")


async def run() -> None:
    await asyncio.gather(
        _trickle_loop(), _stats_loop(), _news_loop(), _reprice_loop()
    )
