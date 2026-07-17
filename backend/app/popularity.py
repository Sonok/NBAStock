"""Real popularity signal: Wikipedia pageviews per player.

Wikimedia's pageviews API is free, keyless, and tracks public attention
remarkably well — stars pull millions of views a season, role players pull
thousands. Sums monthly views across the season (Oct–Jun) for each player's
English Wikipedia article. Falls back to "Name (basketball)" when the plain
title 404s (players who share a name with someone more famous).

Twitter/X sentiment would be the richer signal but the API is paid; this is
the free real-world signal, swappable later.

Run directly to refresh:  python -m app.popularity [--season 2025-26]
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_SEASON = "2025-26"
# Daily granularity: monthly rollups 404 for some articles, daily never does.
API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{title}/daily/{start}/{end}"
)
# Wikimedia asks for a descriptive User-Agent with contact info.
HEADERS = {"User-Agent": "NBAStock/0.1 (student project; ctmahapa95@gmail.com)"}
DECAY_HALF_LIFE_DAYS = 60  # attention is a decaying stock, not a window:
                           # a Finals run keeps ~2/3 of its weight a month on
WORKERS = 4  # Wikimedia throttles aggressive anonymous clients
TIMEOUT = 15
MAX_RETRIES = 4


def decayed_attention(daily: dict[str, dict[str, int]], half_life_days: int | None = None) -> dict[str, float]:
    """player_id_str -> exponentially-decayed view sum as of the newest date
    in the dataset. S_t = S_(t-1) * lambda + views_t, with lambda set by
    DECAY_HALF_LIFE_DAYS. Smooth momentum without a window cliff."""
    from datetime import date as _date

    lam = 0.5 ** (1.0 / (half_life_days or DECAY_HALF_LIFE_DAYS))

    def to_ord(d: str) -> int:
        return _date(int(d[:4]), int(d[4:6]), int(d[6:8])).toordinal()

    latest = max((max(s) for s in daily.values() if s), default=None)
    if latest is None:
        return {}
    latest_o = to_ord(latest)

    out: dict[str, float] = {}
    for pid, series in daily.items():
        s_val, last_o = 0.0, None
        for d in sorted(series):
            o = to_ord(d)
            if last_o is not None:
                s_val *= lam ** (o - last_o)
            s_val += series[d]
            last_o = o
        if last_o is not None:
            s_val *= lam ** (latest_o - last_o)
        out[pid] = s_val
    return out


def cache_path(season: str) -> Path:
    return DATA_DIR / f"popularity_{season}.json"


def _season_window(season: str) -> tuple[str, str]:
    """'2025-26' -> Oct 1 through June 30, extended day by day through the
    offseason (until the next season starts) so daily refreshes keep the
    market moving on draft/free-agency/trade attention."""
    from datetime import date, timedelta

    start_year = int(season.split("-")[0])
    season_end = f"{start_year + 1}0630"
    next_season = f"{start_year + 1}1001"
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    end = min(max(yesterday, season_end), next_season)
    return f"{start_year}1001", end


def _views_for_title(
    session: requests.Session, title: str, start: str, end: str
) -> dict[str, int] | None:
    """Daily views for one article: {'YYYYMMDD': views}. None if no article."""
    url = API.format(title=quote(title.replace(" ", "_"), safe=""), start=start, end=end)
    for attempt in range(MAX_RETRIES):
        resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:  # throttled: honor Retry-After and back off
            import time

            time.sleep(float(resp.headers.get("retry-after", 1)) + attempt)
            continue
        resp.raise_for_status()
        return {
            item["timestamp"][:8]: item["views"]
            for item in resp.json().get("items", [])
        }
    raise requests.RequestException(f"still throttled after {MAX_RETRIES} tries: {title}")


def _player_views(
    session: requests.Session, name: str, start: str, end: str
) -> dict[str, int]:
    # Fetch BOTH candidate titles and keep the higher-traffic one. Neither
    # alone is safe: plain "Anthony Edwards" is the actor, while "Stephen
    # Curry (basketball)" is a low-traffic stub. The real article dominates.
    best: dict[str, int] = {}
    for title in (name, f"{name} (basketball)"):
        try:
            series = _views_for_title(session, title, start, end)
        except requests.RequestException:
            series = None
        if series is not None and sum(series.values()) > sum(best.values()):
            best = series
    return best


def update_player_views(
    session: requests.Session,
    season: str,
    player_id: int,
    name: str,
    days: int = 45,
) -> int:
    """Incremental per-player update: fetch the last `days` of attention and
    upsert into the store. This is the async trickle's unit of work. Returns
    the number of days written. Always touches views_updated_at (via the
    upsert) so hopeless names don't hog the queue."""
    from datetime import date, timedelta

    from . import store

    start_season, end = _season_window(season)
    start = max(
        start_season, (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    )
    series = _player_views(session, name, start, end)
    store.upsert_daily_views(season, player_id, series)
    return len(series)


def refresh(season: str = DEFAULT_SEASON) -> dict:
    """Fetch season pageviews for every cached player and write the cache."""
    from . import ingest  # late import to avoid a cycle

    players = ingest.load(season)["players"]
    start, end = _season_window(season)
    daily: dict[str, dict[str, int]] = {}

    session = requests.Session()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_player_views, session, row["PLAYER_NAME"], start, end): row
            for row in players
        }
        done = 0
        for future in as_completed(futures):
            row = futures[future]
            daily[str(row["PLAYER_ID"])] = future.result()
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(players)} players")

    # Second pass, sequential: empties are usually transient throttle
    # failures, not genuinely unknown players. One calm retry each.
    empties = [row for row in players if not daily.get(str(row["PLAYER_ID"]))]
    if empties:
        print(f"  retrying {len(empties)} players that returned nothing")
        for row in empties:
            daily[str(row["PLAYER_ID"])] = _player_views(
                session, row["PLAYER_NAME"], start, end
            )

    payload = {
        "season": season,
        "source": "wikipedia-pageviews",
        "window": [start, end],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "views": {pid: sum(series.values()) for pid, series in daily.items()},
        "daily": daily,
    }
    DATA_DIR.mkdir(exist_ok=True)
    cache_path(season).write_text(json.dumps(payload))
    return payload


def load(season: str = DEFAULT_SEASON) -> dict[str, int]:
    """Cached player_id -> season pageviews; empty dict if never fetched."""
    path = cache_path(season)
    if not path.exists():
        return {}
    return json.loads(path.read_text())["views"]


def load_daily(season: str = DEFAULT_SEASON) -> dict[str, dict[str, int]]:
    """Cached player_id -> {'YYYYMMDD': views}; empty if never fetched."""
    path = cache_path(season)
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("daily", {})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh Wikipedia popularity data")
    parser.add_argument("--season", default=DEFAULT_SEASON)
    args = parser.parse_args()
    result = refresh(args.season)
    top = sorted(result["views"].items(), key=lambda kv: kv[1], reverse=True)[:5]
    print(f"Fetched pageviews for {len(result['views'])} players")
    print("Top 5 by views:", top)
