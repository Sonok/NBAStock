"""News collector: what the league is talking about -> the events feed.

Sources, aggregated and deduped by headline:
- ESPN's news API (tags athletes -> precise player linkage)
- Google News RSS for "NBA" — surfaces whatever is popular across every
  outlet (The Athletic, Yahoo, Bleacher Report, team beats) all day long
- CBS Sports' NBA wire (RSS)

Player linkage: ESPN athlete ids where available; otherwise a full-name
match against the priced pool in the headline text.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import requests

from . import ingest, store

# team nicknames for relevance-checking general-press headlines
TEAM_WORDS = {n.split()[-1].lower() for n in ingest.TEAM_NAME_TO_ABBR}

NEWS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?limit=20"
RSS_SOURCES = [
    ("google", "https://news.google.com/rss/search?q=NBA%20basketball&hl=en-US&gl=US&ceid=US:en", 10),
    ("cbs", "https://www.cbssports.com/rss/headlines/nba/", 8),
]
SEEN_KEY = "seen_news_ids"
SEEN_CAP = 600


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:80]


def _rss_headlines(url: str, cap: int) -> list[tuple[str, str]]:
    """[(title, link)] from an RSS feed; Google's trailing ' - Outlet' kept
    off the headline."""
    r = requests.get(url, headers=ingest.BROWSER_HEADERS, timeout=20)
    r.raise_for_status()
    items = []
    for it in ET.fromstring(r.content).findall(".//item")[: cap * 2]:
        title = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
        title = re.sub(r"\s+-\s+[^-]{2,40}$", "", title)  # strip source suffix
        link = (it.findtext("link") or "").strip()
        if 12 <= len(title) <= 160 and link:
            items.append((title, link))
        if len(items) >= cap:
            break
    return items


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

    # --- popular-press sweep (Google News + CBS), deduped by headline
    name_index = [
        (r["name"].lower(), r) for r in players_by_norm.values()
    ]
    for source, url, cap in RSS_SOURCES:
        try:
            headlines = _rss_headlines(url, cap)
        except (requests.RequestException, ET.ParseError):
            continue
        for title, link in headlines:
            key = _norm_title(title)
            if not key or key in seen_set:
                continue
            low = title.lower()
            # earliest-mentioned player wins the tag (headline subject first)
            best_pos, player_id, player_name = len(low) + 1, 0, ""
            for lname, row in name_index:
                pos = low.find(lname)
                if 0 <= pos < best_pos:
                    best_pos, player_id, player_name = pos, row["player_id"], row["name"]
            # general-press feeds mix sports: require a basketball anchor
            relevant = (
                "nba" in low
                or player_id != 0
                or any(w in low for w in TEAM_WORDS)
            )
            if not relevant:
                continue
            seen.append(key)
            seen_set.add(key)
            store.add_event(season, player_id, player_name, "news", title, url=link)
            added += 1

    store.set_meta(SEEN_KEY, json.dumps(seen[-SEEN_CAP:]))
    return added
