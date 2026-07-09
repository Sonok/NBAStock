"""NBAStock pricing engine v0.

Turns per-game season stats into a share price per player.

    composite = W_PERF * perf_z + W_POP * pop_z + W_TEAM * team_z + W_MOM * momentum_z
    price     = BASE_PRICE * exp(SPREAD * composite)

All component scores are z-scores computed across qualified players, so the
model is self-calibrating each season: a player's price reflects how far they
sit from the league average on each axis.

Component notes
- performance: classic Game Score (Hollinger) built from per-game box stats.
- popularity:  real-world attention (Wikipedia pageviews over the season,
  log-scaled — fame is power-law distributed) blended with on-court star
  power (scoring volume + minutes + highlight games). Falls back to star
  power alone when pageview data hasn't been fetched.
- team:        win% of the player's team in games they appeared in.
- momentum:    last-10-games Game Score minus season Game Score. Small weight,
  but it makes prices drift on recent form like a real market.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

W_PERF = 0.50
W_POP = 0.22
W_TEAM = 0.18
W_MOM = 0.10

BASE_PRICE = 30.0   # price of a perfectly league-average player
SPREAD = 0.85       # how hard the price separates stars from role players
MIN_PRICE = 1.00
MAX_PRICE = 1500.00

# Qualification floor: below this, stats are too noisy to price fairly.
MIN_GAMES = 15
MIN_MINUTES = 12.0


@dataclass
class PlayerInputs:
    player_id: int
    name: str
    team_id: int
    team_abbr: str
    games_played: int
    minutes: float
    points: float
    rebounds: float
    off_rebounds: float
    def_rebounds: float
    assists: float
    steals: float
    blocks: float
    turnovers: float
    fouls: float
    fgm: float
    fga: float
    ftm: float
    fta: float
    fg3m: float
    team_win_pct: float
    double_doubles: int
    triple_doubles: int
    plus_minus: float
    last10_game_score: float | None = None
    wiki_views: int | None = None  # season Wikipedia pageviews (real popularity)


@dataclass
class PricedPlayer:
    player_id: int
    name: str
    team_id: int
    team_abbr: str
    price: float
    composite: float
    perf_z: float
    pop_z: float
    team_z: float
    momentum_z: float
    game_score: float
    tier: str
    wiki_views: int | None = None
    stats: dict = field(default_factory=dict)


def game_score(p: PlayerInputs) -> float:
    """Hollinger Game Score on per-game averages."""
    return (
        p.points
        + 0.4 * p.fgm
        - 0.7 * p.fga
        - 0.4 * (p.fta - p.ftm)
        + 0.7 * p.off_rebounds
        + 0.3 * p.def_rebounds
        + p.steals
        + 0.7 * p.assists
        + 0.7 * p.blocks
        - 0.4 * p.fouls
        - p.turnovers
    )


def star_power(p: PlayerInputs) -> float:
    """Popularity proxy v0: volume scorers on big minutes with highlight games."""
    dd_rate = p.double_doubles / p.games_played if p.games_played else 0.0
    td_rate = p.triple_doubles / p.games_played if p.games_played else 0.0
    return p.points + 0.35 * p.minutes + 8.0 * dd_rate + 25.0 * td_rate


def _zscores(values: list[float]) -> list[float]:
    n = len(values)
    if n < 2:
        return [0.0] * n
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    if std == 0:
        return [0.0] * n
    return [(v - mean) / std for v in values]


def _tier(composite: float) -> str:
    if composite >= 2.0:
        return "S"
    if composite >= 1.0:
        return "A"
    if composite >= 0.0:
        return "B"
    if composite >= -1.0:
        return "C"
    return "D"


def qualifies(p: PlayerInputs) -> bool:
    return p.games_played >= MIN_GAMES and p.minutes >= MIN_MINUTES


def price_players(players: list[PlayerInputs]) -> list[PricedPlayer]:
    """Price every qualified player against the league distribution."""
    pool = [p for p in players if qualifies(p)]
    if not pool:
        return []

    gs = [game_score(p) for p in pool]
    perf_z = _zscores(gs)
    star_z = _zscores([star_power(p) for p in pool])

    # Popularity: real attention (log pageviews — fame is power-law) blended
    # with on-court star power. Players missing pageview data get the pool
    # median so they aren't punished for a bad name→article match.
    with_views = [p.wiki_views for p in pool if p.wiki_views]
    if with_views:
        median_views = sorted(with_views)[len(with_views) // 2]
        wiki_z = _zscores(
            [math.log10((p.wiki_views or median_views) + 1) for p in pool]
        )
        pop_z = [0.65 * w + 0.35 * s for w, s in zip(wiki_z, star_z)]
    else:
        pop_z = star_z

    team_z = _zscores([p.team_win_pct for p in pool])

    mom_raw = [
        (p.last10_game_score - g) if p.last10_game_score is not None else 0.0
        for p, g in zip(pool, gs)
    ]
    mom_z = _zscores(mom_raw)

    priced: list[PricedPlayer] = []
    for i, p in enumerate(pool):
        composite = (
            W_PERF * perf_z[i]
            + W_POP * pop_z[i]
            + W_TEAM * team_z[i]
            + W_MOM * mom_z[i]
        )
        price = BASE_PRICE * math.exp(SPREAD * composite)
        price = max(MIN_PRICE, min(MAX_PRICE, round(price, 2)))
        priced.append(
            PricedPlayer(
                player_id=p.player_id,
                name=p.name,
                team_id=p.team_id,
                team_abbr=p.team_abbr,
                price=price,
                composite=round(composite, 4),
                perf_z=round(perf_z[i], 4),
                pop_z=round(pop_z[i], 4),
                team_z=round(team_z[i], 4),
                momentum_z=round(mom_z[i], 4),
                game_score=round(gs[i], 2),
                tier=_tier(composite),
                wiki_views=p.wiki_views,
                stats={
                    "gp": p.games_played,
                    "min": p.minutes,
                    "pts": p.points,
                    "reb": p.rebounds,
                    "ast": p.assists,
                    "stl": p.steals,
                    "blk": p.blocks,
                    "team_win_pct": p.team_win_pct,
                },
            )
        )

    priced.sort(key=lambda pp: pp.price, reverse=True)
    return priced
