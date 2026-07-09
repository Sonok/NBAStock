"""News collector: ESPN NBA headlines -> the events feed.

ESPN's public news API is free and tags articles with athlete ids, which we
map back to our players through the ESPN id index (name-matched). Unmatched
articles still land in the feed as league-wide news. Deduped by article id
across runs (rolling window in meta).
"""

from __future__ import annotations

import json

import requests

from . import ingest, store

NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=20"
SEEN_KEY = "seen_news_ids"
SEEN_CAP = 300


def collect(season: str = ingest.DEFAULT_SEASON) -> int:
    """Fetch latest headlines, add unseen ones as events. Returns # added."""
    resp = requests.get(NEWS_URL, headers=ingest.BROWSER_HEADERS, timeout=20)
    resp.raise_for_status()
    articles = resp.json().get("articles", [])

    seen: list[str] = json.loads(store.get_meta(SEEN_KEY) or "[]")
    seen_set = set(seen)
    espn_to_name = {v: k for k, v in ingest.espn_id_index().items()}
    players_by_norm = {
        ingest._normalize_name(r["name"]): r for r in store.get_players(season)
    }

    added = 0
    for a in reversed(articles):  # oldest first so the feed reads forward
        aid = str(a.get("dataSourceIdentifier") or a.get("id") or a.get("headline"))
        headline = a.get("headline")
        if not headline or aid in seen_set:
            continue
        url = a.get("links", {}).get("web", {}).get("href")

        player_id, player_name = 0, ""
        for c in a.get("categories", []):
            if c.get("type") == "athlete":
                norm = espn_to_name.get(str(c.get("athleteId", "")))
                p = players_by_norm.get(norm) if norm else None
                if p:
                    player_id, player_name = p["player_id"], p["name"]
                    break

        store.add_event(season, player_id, player_name, "news", headline, url=url)
        seen.append(aid)
        seen_set.add(aid)
        added += 1

    store.set_meta(SEEN_KEY, json.dumps(seen[-SEEN_CAP:]))
    return added
