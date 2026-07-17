"""Async background collectors + the adaptive reprice loop.

Runs inside the FastAPI process (started from the app's lifespan). Five
independent loops, all writing to the store:

  trickle   refresh the stalest player's attention data, one small
            Wikimedia call at a time
  stats     Basketball-Reference season stats, once per STATS_HOURS
  news      ESPN NBA headlines into the events feed
  signals   pluggable event detectors (signals.py) — trade/injury buzz,
            attention spikes, live games; they front-run the trickle queue
            and flip tempo to `live` for a window
  plays     minute-by-minute notable plays (games.py) while games are live —
            dunks, alley-oops, blocks, clutch threes, straight into the feed
  rosters   ESPN live rosters vs stored teams every 6h — offseason trades
            and signings reassign the player, reprice both rosters, and
            land in the feed ("Roster move: LeBron James → MIA")
  career    slow info-dump aggregator (profile.py) — one player per cycle,
            full league every ~5 weeks: career awards, highlights, draft,
            schools, medals, bio, shot zones
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

from . import games, ingest, market, news, popularity, profile, signals, store

log = logging.getLogger("nbastock.scheduler")

TEMPOS = {
    "live": {"trickle": 20, "reprice_poll": 15},
    "normal": {"trickle": 90, "reprice_poll": 60},
    "idle": {"trickle": 600, "reprice_poll": 300},
}
STATS_HOURS = 24
NEWS_SECONDS = 900
SIGNALS_SECONDS = 120
PLAYS_SECONDS = 20      # play-by-play cadence while games are live
PLAYS_IDLE_SECONDS = 300  # how often to re-check when nothing is live
ROSTERS_HOURS = 6  # offseason moves land within hours of being official
CAREER_SECONDS = 7200   # one player's career/profile re-aggregated per cycle
                        # (~400 priced players -> full league every ~5 weeks)
SEASON = ingest.DEFAULT_SEASON


def current_tempo() -> dict:
    """Baseline from NBASTOCK_TEMPO; signals can override to `live` for a
    window (games in progress, breaking trade/injury news)."""
    override = store.get_meta("tempo_override")
    if override:
        mode, _, expiry = override.partition("|")
        if mode in TEMPOS and expiry:
            if datetime.fromisoformat(expiry) > datetime.now(timezone.utc):
                return TEMPOS[mode]
    return TEMPOS.get(os.environ.get("NBASTOCK_TEMPO", "normal"), TEMPOS["normal"])


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
        await asyncio.sleep(current_tempo()["trickle"])


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


async def _signals_loop() -> None:
    while True:
        try:
            summary = await asyncio.to_thread(signals.run, SEASON)
            if summary.get("signals"):
                log.info("signals: %s", summary)
        except Exception:
            log.exception("signals failed")
        await asyncio.sleep(SIGNALS_SECONDS)


async def _plays_loop() -> None:
    """Minute-by-minute game moments. The game-window detector maintains the
    games_live flag; while it's set, poll every game's play-by-play on a
    tight cadence and surface notable plays (dunks, blocks, clutch threes)."""
    while True:
        live = store.get_meta("games_live") == "1"
        if live:
            try:
                added = await asyncio.to_thread(games.collect_live, SEASON)
                if added:
                    log.info("plays: %d notable plays", added)
            except Exception:
                log.exception("plays collection failed")
        await asyncio.sleep(PLAYS_SECONDS if live else PLAYS_IDLE_SECONDS)


async def _rosters_loop() -> None:
    """Roster truth: compare stored teams against ESPN's live rosters and
    apply trades/signings the moment they're official. A move reprices the
    player AND both rosters (team, direction, teammate-quality factors)."""
    while True:
        try:
            if _hours_since(store.get_meta("last_rosters_check")) >= ROSTERS_HOURS:
                _, team_of = await asyncio.to_thread(ingest.fetch_espn_rosters)
                if team_of:
                    moves = await asyncio.to_thread(
                        store.apply_roster_moves, SEASON, team_of
                    )
                    prices = store.price_map(SEASON)
                    for m in moves:
                        store.mark_priority(SEASON, [m["player_id"]])
                        # every move reprices; only rotation-player moves are
                        # wire-worthy (feed editorial rule: stories, not noise)
                        if prices.get(m["player_id"], 0) >= 30:
                            store.add_event(
                                SEASON, m["player_id"], m["name"], "signal",
                                f"Roster move: {m['name']} → {m['to']} (from {m['from']})",
                            )
                    if moves:
                        log.info("rosters: %d moves applied", len(moves))
                store.set_meta(
                    "last_rosters_check", datetime.now(timezone.utc).isoformat()
                )
        except Exception:
            log.exception("roster check failed")
        await asyncio.sleep(3600)


async def _career_loop() -> None:
    """Slow info-dump aggregator: every cycle, rebuild one player's full
    scouting profile — career awards (bbref bling), Wikipedia highlights,
    draft line, schools, medals, bio, shot zones. The whole league turns
    over every month or so, keeping resumes fresh without hammering
    anyone's servers."""
    while True:
        try:
            pid = await asyncio.to_thread(store.stalest_profile, SEASON)
            if pid is not None:
                await asyncio.to_thread(profile.get, SEASON, pid, True)
                log.info("career: refreshed profile for %s", pid)
        except Exception:
            log.exception("career aggregation failed")
        await asyncio.sleep(CAREER_SECONDS)


async def _reprice_loop() -> None:
    last_version = store.get_meta("data_version")
    while True:
        await asyncio.sleep(current_tempo()["reprice_poll"])
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
        _trickle_loop(), _stats_loop(), _news_loop(), _signals_loop(),
        _plays_loop(), _career_loop(), _rosters_loop(), _reprice_loop(),
    )
