"""Player scouting profiles: 2K-style ratings, bio, nickname, shot zones.

Assembled lazily the first time a player's page asks for it, then cached in
the store (the season is over — none of this moves).

  ratings     percentile-based 0-99 attributes computed from our own stats
              (the honest version of 2K ratings), plus derived strengths /
              weaknesses and an overall
  bio         Wikipedia summary API — first paragraph + link
  nickname    parsed from the Wikipedia infobox (lead-section wikitext)
  shot_zones  Basketball-Reference player page "Shooting" table: share of
              attempts and FG% by distance band (the zone-chart data;
              stats.nba.com's x/y shot detail is ISP-blocked)
"""

from __future__ import annotations

import math
import re
from urllib.parse import quote

import pandas as pd
import requests

from . import ingest, store

WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
WIKI_WIKITEXT = (
    "https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles={title}"
    "&rvslots=main&rvprop=content&rvsection=0&format=json&formatversion=2"
)
BBREF_PLAYER = "https://www.basketball-reference.com/players/{initial}/{bbref_id}.html"
HEADERS = ingest.BROWSER_HEADERS

RATING_KEYS = [
    ("scoring", "Scoring"),
    ("playmaking", "Playmaking"),
    ("rebounding", "Rebounding"),
    ("defense", "Defense"),
    ("efficiency", "Efficiency"),
    ("endurance", "Endurance"),
    ("star_power", "Star power"),
]

ZONES = ["0-3", "3-10", "10-16", "16-3P", "3P"]


# ------------------------------------------------------------- ratings

def _percentile_99(values: list[float], v: float) -> int:
    below = sum(1 for x in values if x < v)
    return round(25 + 74 * below / max(len(values) - 1, 1))  # floor 25, ceil 99


def _raw_metrics(r: dict) -> dict[str, float]:
    ts_denom = 2 * (r["fga"] + 0.44 * r["fta"])
    return {
        "scoring": r["pts"],
        "playmaking": r["ast"] - 0.7 * r["tov"],
        "rebounding": r["reb"],
        "defense": r["stl"] + 1.2 * r["blk"],
        "efficiency": r["pts"] / ts_denom if ts_denom else 0.0,
        "endurance": r["min"] * math.sqrt(r["gp"] / 82),
        "star_power": math.log10((r["wiki_views"] or 1) + 1),
    }


def ratings(season: str, player_id: int) -> dict:
    pool = [r for r in store.get_players(season) if r["price"] is not None]
    me = next((r for r in pool if r["player_id"] == player_id), None)
    if me is None:
        return {}
    metrics = {r["player_id"]: _raw_metrics(r) for r in pool}
    out = {}
    for key, label in RATING_KEYS:
        values = [m[key] for m in metrics.values()]
        out[key] = {"label": label, "value": _percentile_99(values, metrics[player_id][key])}

    composites = sorted(r["composite"] for r in pool)
    overall = 55 + round(44 * sum(1 for c in composites if c < me["composite"]) / max(len(composites) - 1, 1))
    ranked = sorted(out.items(), key=lambda kv: kv[1]["value"], reverse=True)
    return {
        "attributes": [out[k] for k, _ in RATING_KEYS],
        "overall": overall,
        "strengths": [v["label"] for _, v in ranked[:2] if v["value"] >= 70],
        "weaknesses": [v["label"] for _, v in ranked[-2:] if v["value"] <= 55],
    }


# ------------------------------------------------------------- wikipedia

def _wiki_candidates(name: str) -> list[str]:
    return [f"{name} (basketball)", name]


def bio_and_nickname(name: str) -> dict:
    result = {"bio": "", "nickname": [], "wiki_url": ""}
    title_used = None
    for title in _wiki_candidates(name):
        try:
            r = requests.get(
                WIKI_SUMMARY.format(title=quote(title.replace(" ", "_"), safe="")),
                headers=HEADERS, timeout=15,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            blob = (data.get("description", "") + data.get("extract", "")).lower()
            if "basketball" not in blob:
                continue
            result["bio"] = data.get("extract", "")
            result["wiki_url"] = data.get("content_urls", {}).get("desktop", {}).get("page", "")
            title_used = title
            break
        except requests.RequestException:
            continue

    if title_used:
        try:
            r = requests.get(
                WIKI_WIKITEXT.format(title=quote(title_used, safe="")),
                headers=HEADERS, timeout=15,
            )
            content = r.json()["query"]["pages"][0]["revisions"][0]["slots"]["main"]["content"]
            nicknames: list[str] = []
            m = re.search(r"\|\s*nickname\s*=\s*(.+)", content)
            if m:
                raw = m.group(1)
                raw = re.sub(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", raw)
                raw = raw.replace("{{hlist|", "").replace("{{ubl|", "").replace("}}", "")
                for p in re.split(r"\||<br\s*/?>|,", raw):
                    p = re.sub(r"[\[\]\"']", "", p).strip()
                    if 1 < len(p) <= 30 and not p.startswith("{{") and "=" not in p:
                        nicknames.append(p)
            if not nicknames:
                # most articles carry it in prose: nicknamed "the Joker",
                # known by the nickname "King James", ...
                for q in re.findall(
                    r'nickname[sd]?[^"“]{0,40}["“]([^"”]{2,30})["”]', content, re.I
                ):
                    q = re.sub(r"[\[\]']", "", q).strip()
                    if q and q not in nicknames:
                        nicknames.append(q)
            result["nickname"] = nicknames[:3]
        except (requests.RequestException, KeyError, IndexError):
            pass
    return result


# ------------------------------------------------------------- shot zones

def shot_zones(bbref_id: str, season: str) -> list[dict]:
    """Share of FGA and FG% by distance band from the bbref player page."""
    if not bbref_id:
        return []
    year_label = f"{season.split('-')[0]}-{season.split('-')[1]}"
    url = BBREF_PLAYER.format(initial=bbref_id[0], bbref_id=bbref_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        r.encoding = "utf-8"
        html = r.text
    except requests.RequestException:
        return []

    for df in ingest._read_tables(html):
        if not isinstance(df.columns, pd.MultiIndex):
            continue
        tops = {str(t) for t, _ in df.columns}
        if not any("% of FGA by Distance" in t for t in tops):
            continue
        season_col = df.columns[0]
        rows = df[df[season_col].astype(str).str.startswith(year_label)]
        if not len(rows):
            return []
        row = rows.iloc[0]
        zones = []
        for z in ZONES:
            try:
                share = float(row[("% of FGA by Distance", z)])
                pct = float(row[("FG% by Distance", z)])
            except (KeyError, TypeError, ValueError):
                continue
            if not (math.isnan(share) or math.isnan(pct)):
                zones.append({"zone": z, "share": round(share, 3), "fg_pct": round(pct, 3)})
        return zones
    return []


# ------------------------------------------------------------- assembly

def get(season: str, player_id: int, refresh: bool = False) -> dict | None:
    if not refresh:
        cached = store.get_profile(season, player_id)
        if cached is not None:
            return cached
    me = next(
        (r for r in store.get_players(season) if r["player_id"] == player_id), None
    )
    if me is None:
        return None
    profile = {
        "player_id": player_id,
        **bio_and_nickname(me["name"]),
        "ratings": ratings(season, player_id),
        "shot_zones": shot_zones(me.get("bbref_id") or "", season),
    }
    store.set_profile(season, player_id, profile)
    return profile
