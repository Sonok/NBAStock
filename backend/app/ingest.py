"""Fetch real NBA per-game stats and cache them locally.

Primary source: Basketball-Reference season pages (one request for every
player's per-game averages, one for standings). stats.nba.com is the richer
API but silently drops connections on many residential ISPs, so it is not a
dependable default. Player headshots still come from the NBA CDN by resolving
names to official NBA person ids via nba_api's *local* static player list
(no network call).

Cached as JSON under backend/app/data/ — downstream code reads the cache and
refresh is an explicit action. Be polite to Basketball-Reference: a refresh
is 2 requests, never run it in a loop.

Run directly to refresh:  python -m app.ingest [--season 2025-26]
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import zlib
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from nba_api.stats.static import players as static_players

from .pricing import PlayerInputs

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_SEASON = "2025-26"
REQUEST_TIMEOUT = 30

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Basketball-Reference uses a few abbreviations the NBA doesn't.
BBREF_TO_NBA_ABBR = {"BRK": "BKN", "CHO": "CHA", "PHO": "PHX"}

TEAM_NAME_TO_ABBR = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP", "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def cache_path(season: str) -> Path:
    return DATA_DIR / f"players_{season}.json"


def _season_end_year(season: str) -> int:
    """'2025-26' -> 2026 (Basketball-Reference keys seasons by end year)."""
    start = int(season.split("-")[0])
    return start + 1


def _normalize_name(name: str) -> str:
    """Accent-insensitive, suffix-insensitive key for name matching."""
    name = name.replace("ё", "e").replace("Ё", "E")  # Cyrillic ё survives NFKD
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    )
    ascii_name = ascii_name.lower().replace(".", "").replace("'", "")
    ascii_name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", ascii_name)
    return re.sub(r"\s+", " ", ascii_name).strip()


def _nba_id_index() -> dict[str, int]:
    """Normalized full name -> official NBA person id (local data, no network)."""
    return {
        _normalize_name(p["full_name"]): p["id"]
        for p in static_players.get_players()
    }


ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
ESPN_ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"


def espn_id_index() -> dict[str, str]:
    """Normalized player name -> ESPN athlete id, cached on disk. Used for
    headshot fallback and to tie news articles to players. Aggregated from
    the 30 team roster pages — ESPN's athlete index endpoint is partial."""
    path = DATA_DIR / "espn_ids.json"
    if path.exists():
        return json.loads(path.read_text())
    ids: dict[str, str] = {}
    try:
        teams = requests.get(ESPN_TEAMS_URL, headers=BROWSER_HEADERS, timeout=20)
        teams.raise_for_status()
        team_ids = [
            t["team"]["id"]
            for t in teams.json()["sports"][0]["leagues"][0]["teams"]
        ]
        for tid in team_ids:
            r = requests.get(
                ESPN_ROSTER_URL.format(team_id=tid),
                headers=BROWSER_HEADERS,
                timeout=20,
            )
            if r.status_code != 200:
                continue
            for a in r.json().get("athletes", []):
                if a.get("displayName") and a.get("id"):
                    ids[_normalize_name(a["displayName"])] = str(a["id"])
            time.sleep(0.25)
    except (requests.RequestException, KeyError):
        if not ids:
            return {}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(ids))
    return ids


def _get(url: str) -> str:
    resp = requests.get(url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # bbref omits the charset header; requests guesses latin-1
    return resp.text


def _read_tables(html: str) -> list[pd.DataFrame]:
    """read_html, also unhiding tables Basketball-Reference ships in comments."""
    tables = pd.read_html(StringIO(html))
    if "<!--" in html:
        uncommented = html.replace("<!--", "").replace("-->", "")
        try:
            tables += pd.read_html(StringIO(uncommented))
        except ValueError:
            pass
    return tables


def _fetch_standings(year: int) -> dict[str, float]:
    """Team abbreviation -> win pct."""
    html = _get(f"https://www.basketball-reference.com/leagues/NBA_{year}_standings.html")
    win_pct: dict[str, float] = {}
    for df in _read_tables(html):
        first_col = str(df.columns[0])
        if "Conference" not in first_col and "Division" not in first_col:
            continue
        for _, row in df.iterrows():
            raw_name = str(row.iloc[0])
            name = re.sub(r"[*†]|\s*\(\d+\)\s*$", "", raw_name).strip()
            if name in TEAM_NAME_TO_ABBR and "W/L%" in df.columns:
                try:
                    win_pct[TEAM_NAME_TO_ABBR[name]] = float(row["W/L%"])
                except (TypeError, ValueError):
                    continue
    return win_pct


def _fetch_per_game(year: int) -> tuple[pd.DataFrame, dict[str, str]]:
    """The per-game table plus normalized name -> bbref player id (parsed
    from the anchor tags pandas drops; ids unlock bbref player pages for
    shooting zones and future advanced stats)."""
    html = _get(f"https://www.basketball-reference.com/leagues/NBA_{year}_per_game.html")
    bbref_ids = {
        _normalize_name(name): pid
        for pid, name in re.findall(
            r'href="/players/[a-z]/([a-z0-9]+)\.html">([^<]+)</a>', html
        )
    }
    for df in _read_tables(html):
        cols = set(map(str, df.columns))
        if {"Player", "PTS", "TRB", "AST"}.issubset(cols):
            return df, bbref_ids
    raise RuntimeError(f"per-game table not found for {year}")


def _num(row, col, default=0.0) -> float:
    try:
        v = float(row[col])
        return default if pd.isna(v) else v
    except (KeyError, TypeError, ValueError):
        return default


def refresh(season: str = DEFAULT_SEASON) -> dict:
    """Pull fresh data from Basketball-Reference and write the cache file."""
    year = _season_end_year(season)
    df, bbref_ids = _fetch_per_game(year)
    time.sleep(2)  # be polite between requests
    standings = _fetch_standings(year)
    nba_ids = _nba_id_index()

    team_col = "Team" if "Team" in df.columns else "Tm"
    df = df[df["Player"].notna() & (df["Player"] != "Player")]
    df = df[df["Player"] != "League Average"]

    # Traded players appear as a combined "2TM"/"3TM" row plus one row per
    # stint. Use the combined row for stats; the last stint is their current
    # team.
    rows: list[dict] = []
    for name, group in df.groupby("Player", sort=False):
        combined = group[group[team_col].astype(str).str.contains("TM")]
        stat_row = combined.iloc[0] if len(combined) else group.iloc[0]
        team_row = group[~group[team_col].astype(str).str.contains("TM")]
        bbref_abbr = str(team_row.iloc[-1][team_col]) if len(team_row) else str(stat_row[team_col])
        abbr = BBREF_TO_NBA_ABBR.get(bbref_abbr, bbref_abbr)

        norm = _normalize_name(str(name))
        person_id = nba_ids.get(norm)
        rows.append(
            {
                "PLAYER_ID": person_id or zlib.crc32(norm.encode()),
                "PLAYER_NAME": str(name),
                "TEAM_ID": 0,
                "TEAM_ABBREVIATION": abbr,
                "GP": int(_num(stat_row, "G")),
                "MIN": _num(stat_row, "MP"),
                "PTS": _num(stat_row, "PTS"),
                "REB": _num(stat_row, "TRB"),
                "OREB": _num(stat_row, "ORB"),
                "DREB": _num(stat_row, "DRB"),
                "AST": _num(stat_row, "AST"),
                "STL": _num(stat_row, "STL"),
                "BLK": _num(stat_row, "BLK"),
                "TOV": _num(stat_row, "TOV"),
                "PF": _num(stat_row, "PF"),
                "FGM": _num(stat_row, "FG"),
                "FGA": _num(stat_row, "FGA"),
                "FTM": _num(stat_row, "FT"),
                "FTA": _num(stat_row, "FTA"),
                "FG3M": _num(stat_row, "3P"),
                "W_PCT": standings.get(abbr, 0.5),
                "AWARDS": "" if pd.isna(stat_row.get("Awards")) else str(stat_row.get("Awards", "")),
                "BBREF_ID": bbref_ids.get(norm, ""),
                "DD2": 0,   # not in the per-game table; star_power tolerates 0
                "TD3": 0,
                "PLUS_MINUS": 0.0,
            }
        )

    payload = {
        "season": season,
        "source": "basketball-reference",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "players": rows,
        # Last-10-games momentum needs a per-player source; wired up later.
        "last10_game_score": {},
    }
    DATA_DIR.mkdir(exist_ok=True)
    cache_path(season).write_text(json.dumps(payload))
    return payload


def load(season: str = DEFAULT_SEASON, allow_fetch: bool = True) -> dict:
    """Read the cache; fetch once if it doesn't exist yet."""
    path = cache_path(season)
    if path.exists():
        return json.loads(path.read_text())
    if not allow_fetch:
        raise FileNotFoundError(f"No cached data for {season}; run python -m app.ingest")
    return refresh(season)


def _row_to_inputs(
    row: dict,
    last10: dict[str, float] | None = None,
    wiki_views: dict[str, int] | None = None,
) -> PlayerInputs:
    pid = int(row["PLAYER_ID"])
    return PlayerInputs(
        player_id=pid,
        name=row["PLAYER_NAME"],
        team_id=int(row["TEAM_ID"]),
        team_abbr=row["TEAM_ABBREVIATION"],
        games_played=int(row["GP"]),
        minutes=float(row["MIN"]),
        points=float(row["PTS"]),
        rebounds=float(row["REB"]),
        off_rebounds=float(row["OREB"]),
        def_rebounds=float(row["DREB"]),
        assists=float(row["AST"]),
        steals=float(row["STL"]),
        blocks=float(row["BLK"]),
        turnovers=float(row["TOV"]),
        fouls=float(row["PF"]),
        fgm=float(row["FGM"]),
        fga=float(row["FGA"]),
        ftm=float(row["FTM"]),
        fta=float(row["FTA"]),
        fg3m=float(row["FG3M"]),
        team_win_pct=float(row["W_PCT"]),
        double_doubles=int(row.get("DD2", 0)),
        triple_doubles=int(row.get("TD3", 0)),
        plus_minus=float(row["PLUS_MINUS"]),
        last10_game_score=(last10 or {}).get(str(pid)),
        wiki_views=(wiki_views or {}).get(str(pid)),
    )


def player_inputs(season: str = DEFAULT_SEASON) -> list[PlayerInputs]:
    """Cached raw rows -> PlayerInputs ready for the pricing engine."""
    from . import popularity

    data = load(season)
    last10 = data.get("last10_game_score", {})
    wiki_views = popularity.load(season)
    return [_row_to_inputs(row, last10, wiki_views) for row in data["players"]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Refresh cached NBA stats")
    parser.add_argument("--season", default=DEFAULT_SEASON)
    args = parser.parse_args()
    result = refresh(args.season)
    print(f"Fetched {len(result['players'])} players for {result['season']}")
