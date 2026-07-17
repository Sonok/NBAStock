"""Live game play-by-play collector (ESPN).

During live games (the game-window detector already flips the market to
`live` tempo), this polls ESPN's play-by-play for every in-progress game and
pushes NOTABLE plays into the events feed within seconds of them happening:
dunks, alley-oops, blocks, and clutch threes (4th quarter / OT, last 5
minutes). Players who make a notable play jump the attention-polling queue.

Off-season this is idle — the loop only runs while the scoreboard reports
games in progress. ESPN keeps full play-by-play for finished games, which is
how this gets tested in July.
"""

from __future__ import annotations

import json
import re

import requests

from . import ingest, signals, store

SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
SEEN_CAP = 600  # plays per game we remember (a full game has ~500)
CLUTCH_PERIOD = 4
CLUTCH_SECONDS = 5 * 60


def _clock_seconds(display: str) -> float:
    m = re.match(r"(\d+):(\d+)(?:\.\d+)?", display or "")
    if not m:
        return 9_999
    return int(m.group(1)) * 60 + int(m.group(2))


def _notable(play: dict) -> str | None:
    """Classify a play as feed-worthy, or None."""
    text = (play.get("text") or "").lower()
    if ("alley oop" in text or "alley-oop" in text) and play.get("scoringPlay"):
        return "Alley-oop"
    if "dunk" in text and play.get("scoringPlay"):
        return "Dunk"
    if "block" in text:
        return "Block"
    if (
        play.get("scoringPlay")
        and "three point" in text
        and play.get("period", {}).get("number", 0) >= CLUTCH_PERIOD
        and _clock_seconds(play.get("clock", {}).get("displayValue", "")) <= CLUTCH_SECONDS
    ):
        return "Clutch three"
    return None


def _players_by_espn_id(season: str) -> dict[str, dict]:
    espn_index = ingest.espn_id_index()  # normalized name -> espn id
    by_norm = {
        ingest._normalize_name(r["name"]): r for r in store.get_players(season)
    }
    return {
        espn_id: by_norm[norm]
        for norm, espn_id in espn_index.items()
        if norm in by_norm
    }


def collect_game(event_id: str, season: str = ingest.DEFAULT_SEASON) -> int:
    """Fetch one game's play-by-play, add unseen notable plays as events."""
    resp = requests.get(
        SUMMARY_URL.format(event_id=event_id),
        headers=ingest.BROWSER_HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    plays = resp.json().get("plays", [])

    seen_key = f"plays_seen_{event_id}"
    seen: list[str] = json.loads(store.get_meta(seen_key) or "[]")
    seen_set = set(seen)
    players = _players_by_espn_id(season)

    added = 0
    for play in plays:
        play_id = str(play.get("id") or "")
        if not play_id or play_id in seen_set:
            continue
        seen.append(play_id)
        seen_set.add(play_id)

        kind = _notable(play)
        if kind is None:
            continue
        athlete_ids = [
            str(p.get("athlete", {}).get("id", "")) for p in play.get("participants", [])
        ]
        if kind == "Block":
            # ESPN lists [shooter, blocker]; the blocker is the star of the play
            athlete_ids.reverse()
        player = next((players[a] for a in athlete_ids if a in players), None)
        if player is None:
            continue  # only surface plays by players the market prices

        period = play.get("period", {}).get("displayValue", "")
        clock = play.get("clock", {}).get("displayValue", "")
        store.add_event(
            season,
            player["player_id"],
            player["name"],
            "play",
            f"{kind}: {play.get('text')} ({period} {clock})",
        )
        store.mark_priority(season, [player["player_id"]])
        added += 1

    store.set_meta(seen_key, json.dumps(seen[-SEEN_CAP:]))
    return added


def live_event_ids() -> list[str]:
    """IDs of games currently in progress."""
    resp = requests.get(
        signals.SCOREBOARD_URL, headers=ingest.BROWSER_HEADERS, timeout=15
    )
    resp.raise_for_status()
    return [
        str(ev.get("id"))
        for ev in resp.json().get("events", [])
        if ev.get("status", {}).get("type", {}).get("state") == "in"
    ]


def collect_live(season: str = ingest.DEFAULT_SEASON) -> int:
    """One polling pass over all live games. No-op when nothing is live."""
    total = 0
    for event_id in live_event_ids():
        try:
            total += collect_game(event_id, season)
        except requests.RequestException:
            continue
    return total
