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
    "&rvslots=main&rvprop=content&rvsection=0&redirects=1&format=json&formatversion=2"
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

# career award label -> patch tier. Gold = hardware won, silver = teams and
# statistical titles, felt = everything else on the résumé.
GOLD_AWARDS = (
    "MVP", "NBA Champion", "Finals MVP", "DPOY", "ROY", "Scoring Champ",
    "Sixth Man", "Most Improved", "Clutch Player",
)
SILVER_AWARDS = (
    "All-NBA", "All-Star", "All-Defensive", "Rebounding Champ",
    "Assists Champ", "Steals Champ", "Blocks Champ", "Conf. Finals MVP",
)

BLING_LABELS = {
    "All Star": "All-Star",
    "NBA Champ": "NBA Champion",
    "ABA Champ": "ABA Champion",
    "TRB Champ": "Rebounding Champ",
    "AST Champ": "Assists Champ",
    "STL Champ": "Steals Champ",
    "BLK Champ": "Blocks Champ",
    "Scoring Champ": "Scoring Champ",
    "Def. POY": "DPOY",
    "WCF MVP": "Conf. Finals MVP",
    "ECF MVP": "Conf. Finals MVP",
    "AS MVP": "All-Star MVP",
    "6MOY": "Sixth Man",
    "MIP": "Most Improved",
    "CPOY": "Clutch Player",
}


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
    result = {"bio": "", "nickname": [], "wiki_url": "", "_career_wiki": {}}
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
            result["_career_wiki"] = _career_from_wikitext(content)
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
                for match in re.findall(
                    r'nickname[sd]?[^"“]{0,40}["“]([^"”]{2,30})["”]'
                    r'(?:\s*(?:and|,|or)\s*["“]([^"”]{2,30})["”])?'
                    r'(?:\s*(?:and|,|or)\s*["“]([^"”]{2,30})["”])?',
                    content, re.I,
                ):
                    for q in match:
                        q = re.sub(r"[\[\]']", "", q).strip()
                        if q and q not in nicknames:
                            nicknames.append(q)
            result["nickname"] = nicknames[:4]
        except (requests.RequestException, KeyError, IndexError):
            pass
    return result


# ------------------------------------------------------------- career

def _clean_wikitext(s: str) -> str:
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"\{\{nbay\|(\d{4})\|end\}\}", lambda m: str(int(m.group(1)) + 1), s)
    s = re.sub(r"\{\{nasg\|(\d{4})[^}]*\}\}", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", s).strip(" ,;")


def _career_patches(bling: list[str]) -> list[dict]:
    """bbref bling items ('8x All Star', '2023 NBA Champ') -> letterman
    patches with counts and prestige tiers."""
    patches = []
    for item in bling:
        count = 1
        label = item.strip()
        m = re.match(r"(\d+)x\s+(.*)", label)
        if m:
            count = int(m.group(1))
            label = m.group(2).strip()
        # strip a leading season/year ('2023 NBA Champ', '2025-26 TRB Champ')
        label = re.sub(r"^\d{4}(?:-\d{2})?\s+", "", label)
        label = BLING_LABELS.get(label, label)
        # silver first: "Conf. Finals MVP" must not substring-match "Finals MVP"
        tier = (
            "silver" if any(sv in label for sv in SILVER_AWARDS)
            else "gold" if any(g in label for g in GOLD_AWARDS)
            else "felt"
        )
        patches.append({"code": label, "label": label, "tier": tier, "count": count})
    order = {"gold": 0, "silver": 1, "felt": 2}
    patches.sort(key=lambda p: (order[p["tier"]], -p["count"]))
    return patches


def _career_from_wikitext(content: str) -> dict:
    """Infobox career facts: highlights list, draft line, schools, vitals
    (born/birthplace/position/height/weight/years pro), medals."""
    out: dict = {"highlights": [], "draft": None, "high_school": None,
                 "college": None, "medals": [], "birth_place": None,
                 "born": None, "age": None, "position": None,
                 "height": None, "weight": None, "years_pro": None}

    m = re.search(r"\|\s*highlights\s*=\s*(.*?)(?=\n\s*\|\s*\w+\s*=|\n\}\})", content, re.S)
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if line.startswith("*"):
                cleaned = _clean_wikitext(line.lstrip("* "))
                if 2 < len(cleaned) <= 90:
                    out["highlights"].append(cleaned)

    def field(name: str) -> str | None:
        fm = re.search(r"\|\s*" + name + r"\s*=\s*(.+)", content)
        if not fm:
            return None
        val = _clean_wikitext(fm.group(1))
        return val or None

    year, rnd, pick = field("draft_year"), field("draft_round"), field("draft_pick")
    if year and rnd and pick:
        out["draft"] = f"{year} draft · round {rnd}, pick {pick}"
    elif year:
        out["draft"] = f"{year} draft"
    out["high_school"] = field("high_school")
    out["college"] = field("college")
    out["birth_place"] = field("birth_place")
    out["position"] = (field("position") or "")[:40] or None

    bm = re.search(r"\{\{[Bb]irth date(?: and age)?\s*\|(?:df=\w+\|)?(\d{4})\|(\d{1,2})\|(\d{1,2})", content)
    if bm:
        from datetime import date
        y, mo, d = int(bm.group(1)), int(bm.group(2)), int(bm.group(3))
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        out["born"] = f"{months[mo - 1]} {d}, {y}"
        today = date.today()
        out["age"] = today.year - y - ((today.month, today.day) < (mo, d))

    ft, inch = field("height_ft"), field("height_in")
    if ft:
        out["height"] = f"{ft}'{inch or 0}\""
    lb = field("weight_lb") or field("weight_lbs")
    if lb:
        out["weight"] = f"{lb} lb"

    start = field("career_start")
    if start and start.isdigit():
        from datetime import date
        out["years_pro"] = max(date.today().year - int(start), 0)

    for metal, body in re.findall(
        r"\{\{Medal(Gold|Silver|Bronze)\s*\|(.*?)\}\}", content, re.S
    ):
        event = _clean_wikitext(body).replace("|", " · ")
        event = re.sub(r"\s*·\s*", " · ", event).strip(" ·")
        if event:
            out["medals"].append({"metal": metal.lower(), "event": event[:80]})
    return out


def _bling(html: str) -> list[str]:
    m = re.search(r'<ul id="bling">(.*?)</ul>', html, re.S)
    if not m:
        return []
    return [
        _clean_wikitext(item)
        for item in re.findall(r"<li[^>]*>(?:<a[^>]*>)?([^<]+)", m.group(1))
    ]


# ------------------------------------------------------------- shot zones

def _bbref_html(bbref_id: str) -> str:
    if not bbref_id:
        return ""
    url = BBREF_PLAYER.format(initial=bbref_id[0], bbref_id=bbref_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text
    except requests.RequestException:
        return ""


def shot_zones(html: str, season: str) -> list[dict]:
    """Share of FGA and FG% by distance band from the bbref player page."""
    if not html:
        return []
    year_label = f"{season.split('-')[0]}-{season.split('-')[1]}"

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
    wiki = bio_and_nickname(me["name"])
    career_wiki = wiki.pop("_career_wiki", {})
    bbref_html = _bbref_html(me.get("bbref_id") or "")
    profile = {
        "player_id": player_id,
        **wiki,
        "ratings": ratings(season, player_id),
        "shot_zones": shot_zones(bbref_html, season),
        "career": {
            "patches": _career_patches(_bling(bbref_html)),
            **career_wiki,
        },
    }
    store.set_profile(season, player_id, profile)
    return profile
