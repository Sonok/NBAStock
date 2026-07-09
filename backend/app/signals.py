"""Event detection: pluggable detectors that sense "something is happening"
and make the market react.

The skeleton is the point — a Detector is anything with a `name` and a
`detect(season) -> list[Signal]`. Register it in DETECTORS and the scheduler
runs it; processing a Signal is uniform:

  * players it names jump to the FRONT of the attention-trickle queue
  * a tempo boost flips collection to `live` cadence for a window
  * it lands in the events feed (type='signal') so traders see the market
    waking up

Shipping detectors (v0):
  NewsKeywordDetector   trade/injury/signing language in collected headlines
                        (ESPN relays the Shams/Woj announcements)
  AttentionSpikeDetector a player's daily pageviews explode vs their own
                        trailing baseline — something happened, even if we
                        don't know what yet
  GameWindowDetector    live NBA games via ESPN's scoreboard -> `live` tempo
                        for the duration (no-op all offseason)

Future plug-ins follow the same shape: an odds-move detector, a Reddit
comment-velocity detector, a direct social-feed watcher.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from . import ingest, store

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

SPIKE_RATIO = 3.0      # yesterday >= 3x the player's 30d daily average
SPIKE_MIN_VIEWS = 8000  # ...and big enough in absolute terms to matter


@dataclass
class Signal:
    kind: str                    # "trade_rumor" | "injury" | "signing" | "attention_spike" | "game_live"
    message: str                 # feed-facing text
    player_ids: list[int] = field(default_factory=list)
    primary_name: str = ""       # feed attribution (empty = league-wide)
    tempo_boost_minutes: int = 0


class NewsKeywordDetector:
    """Headline language -> market reaction. Processes each news event once."""

    name = "news_keywords"

    KINDS = {
        "trade_rumor": ("trade", "traded", "trading", "deal for", "acquire", "acquiring"),
        "injury": ("injury", "injured", "out for", "tear", "torn", "surgery", "fracture", "sprain", "mri"),
        "signing": ("sign", "signs", "signing", "agrees to", "waive", "waived", "buyout", "extension"),
    }

    def detect(self, season: str) -> list[Signal]:
        last_id = int(store.get_meta("signals_last_news_id") or 0)
        news = [
            e for e in store.events_since(last_id, limit=100) if e["type"] == "news"
        ]
        if news:
            store.set_meta("signals_last_news_id", str(max(e["id"] for e in news)))

        out: list[Signal] = []
        for e in news:
            text = e["message"].lower()
            kind = next(
                (k for k, words in self.KINDS.items() if any(w in text for w in words)),
                None,
            )
            if kind is None or not e["player_id"]:
                continue  # only react when the story names a player we price
            label = kind.replace("_", " ")
            out.append(
                Signal(
                    kind=kind,
                    message=f"{label.capitalize()} buzz: {e['name']} — market watching ({e['message'][:80]})",
                    player_ids=[e["player_id"]],
                    primary_name=e["name"],
                    tempo_boost_minutes=30,
                )
            )
        return out


class AttentionSpikeDetector:
    """Yesterday's pageviews vs the player's own trailing baseline. Fires at
    most once per player per data-day (cooldown tracked in meta)."""

    name = "attention_spike"

    def detect(self, season: str) -> list[Signal]:
        daily = store.get_daily_views(season)
        players = {r["player_id"]: r["name"] for r in store.get_players(season)}
        fired: dict[str, str] = json.loads(store.get_meta("spike_cooldowns") or "{}")

        out: list[Signal] = []
        for pid_str, series in daily.items():
            pid = int(pid_str)
            if pid not in players or len(series) < 10:
                continue
            dates = sorted(series)
            latest = dates[-1]
            if fired.get(pid_str) == latest:
                continue
            baseline_days = dates[-31:-1]
            baseline = sum(series[d] for d in baseline_days) / max(len(baseline_days), 1)
            views = series[latest]
            if baseline > 0 and views >= SPIKE_MIN_VIEWS and views / baseline >= SPIKE_RATIO:
                fired[pid_str] = latest
                out.append(
                    Signal(
                        kind="attention_spike",
                        message=(
                            f"Attention spike: {players[pid]} — {views:,} pageviews "
                            f"({views / baseline:.0f}x their normal day)"
                        ),
                        player_ids=[pid],
                        primary_name=players[pid],
                        tempo_boost_minutes=15,
                    )
                )
        store.set_meta("spike_cooldowns", json.dumps(fired))
        return out


class GameWindowDetector:
    """Live games -> live tempo. Emits a feed signal only on the quiet->live
    transition; keeps refreshing the tempo boost while games run."""

    name = "game_window"

    def detect(self, season: str) -> list[Signal]:
        resp = requests.get(SCOREBOARD_URL, headers=ingest.BROWSER_HEADERS, timeout=15)
        resp.raise_for_status()
        live = [
            ev for ev in resp.json().get("events", [])
            if ev.get("status", {}).get("type", {}).get("state") == "in"
        ]
        was_live = store.get_meta("games_live") == "1"
        store.set_meta("games_live", "1" if live else "0")
        if not live:
            return []
        signal = Signal(
            kind="game_live",
            message=f"{len(live)} game{'s' if len(live) != 1 else ''} live — market on game-time cadence",
            tempo_boost_minutes=20,  # refreshed every detector cycle while live
        )
        if was_live:
            signal.message = ""  # keep boosting, but don't re-announce in the feed
        return [signal]


DETECTORS = [NewsKeywordDetector(), AttentionSpikeDetector(), GameWindowDetector()]


def run(season: str = ingest.DEFAULT_SEASON) -> dict:
    """Run every detector, apply every signal. Detector failures are isolated."""
    signals: list[Signal] = []
    errors = 0
    for det in DETECTORS:
        try:
            signals.extend(det.detect(season))
        except Exception:
            errors += 1

    for s in signals:
        if s.player_ids:
            store.mark_priority(season, s.player_ids)
        if s.tempo_boost_minutes:
            expiry = datetime.now(timezone.utc) + timedelta(minutes=s.tempo_boost_minutes)
            store.set_meta("tempo_override", f"live|{expiry.isoformat()}")
        if s.message:
            store.add_event(
                season,
                s.player_ids[0] if s.player_ids else 0,
                s.primary_name,
                "signal",
                s.message,
            )
    return {"signals": len(signals), "detector_errors": errors}
