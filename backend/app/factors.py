"""The multi-factor pricing engine.

Every input to a player's price is a Factor: an object that scores the whole
player pool on one dimension. The engine z-scores each factor across the
pool, applies season-phase weights, and sums into the composite that sets
the price. Adding a signal to the market = subclassing Factor (or, for
sentiment, subclassing SentimentProvider) and registering it — no other code
changes.

Phase awareness: weights shift with the calendar. In the offseason the
volatile factors (popularity, momentum, sentiment) are damped hard, so
prices are deliberately stagnant; in the regular season they open up; in
the playoffs momentum and attention matter most. See WEIGHTS.

Full model documentation and the ideas backlog live in MODEL.md.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

from .pricing import PlayerInputs, game_score, star_power

# ------------------------------------------------------------- phases

def current_phase(today: date | None = None) -> str:
    m = (today or date.today()).month
    if m in (7, 8, 9):
        return "offseason"
    if m in (4, 5, 6):
        return "playoffs"
    return "regular"


# factor weights per phase — each column sums to 1.0
WEIGHTS: dict[str, dict[str, float]] = {
    #                offseason  regular  playoffs
    "performance":  {"offseason": 0.42, "regular": 0.40, "playoffs": 0.42},
    "projection":   {"offseason": 0.15, "regular": 0.08, "playoffs": 0.05},
    "popularity":   {"offseason": 0.12, "regular": 0.18, "playoffs": 0.20},
    "momentum":     {"offseason": 0.04, "regular": 0.10, "playoffs": 0.12},
    "team":         {"offseason": 0.10, "regular": 0.08, "playoffs": 0.08},
    "team_direction": {"offseason": 0.08, "regular": 0.04, "playoffs": 0.02},
    "teammates":    {"offseason": 0.05, "regular": 0.04, "playoffs": 0.04},
    "sentiment":    {"offseason": 0.04, "regular": 0.05, "playoffs": 0.05},
    "matchup":      {"offseason": 0.00, "regular": 0.03, "playoffs": 0.02},
}


@dataclass
class MarketContext:
    pool: list[PlayerInputs]
    phase: str
    by_team: dict[str, list[PlayerInputs]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for p in self.pool:
            self.by_team.setdefault(p.team_abbr, []).append(p)


# ------------------------------------------------------------- base class

class Factor(ABC):
    """One dimension of player value. `raw` returns an unscaled score per
    player (higher = better); return None for players the factor can't
    assess — they get the pool median instead of a penalty."""

    name: str = ""
    label: str = ""

    @abstractmethod
    def raw(self, ctx: MarketContext) -> dict[int, float | None]: ...


# ------------------------------------------------------------- factors

class PerformanceFactor(Factor):
    """On-court production: Hollinger Game Score from per-game box stats."""

    name, label = "performance", "Perf"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        return {p.player_id: game_score(p) for p in ctx.pool}


class ProjectionFactor(Factor):
    """Predictive: expected next-season production off the NBA aging curve.
    A 21-year-old's Game Score is projected to grow ~10%; a 34-year-old's to
    fade ~10%. This is where 'how good is this player GOING to be' lives —
    replaceable later by a learned career-curve model (see MODEL.md)."""

    name, label = "projection", "Proj"

    @staticmethod
    def age_delta(age: float) -> float:
        if age <= 21:
            return 0.10
        if age <= 23:
            return 0.06
        if age <= 25:
            return 0.03
        if age <= 28:
            return 0.0
        if age <= 30:
            return -0.03
        if age <= 33:
            return -0.06
        return -0.10

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        return {
            p.player_id: game_score(p) * (1 + self.age_delta(p.age))
            for p in ctx.pool
        }


class PopularityFactor(Factor):
    """Real-world attention: exponentially decayed Wikipedia pageviews
    (60-day half-life — a Finals run doesn't evaporate), blended with
    on-court star power. Log-scaled: fame is power-law distributed."""

    name, label = "popularity", "Pop"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        out: dict[int, float | None] = {}
        for p in ctx.pool:
            views = p.wiki_views_recent if p.wiki_views_recent is not None else p.wiki_views
            out[p.player_id] = (
                math.log10(views + 1) + 0.02 * star_power(p) if views else None
            )
        return out


class MomentumFactor(Factor):
    """Is the player 'on a roll'? Ratio of short-half-life attention (7d) to
    long (60d), against the steady-state ratio — positive when attention is
    accelerating, negative when a spike is cooling. In-season this will also
    blend last-10-games form once per-game logs land (see MODEL.md)."""

    name, label = "momentum", "Mom"

    # steady-state short/long ratio when daily views are constant
    _STEADY = (1 - 0.5 ** (1 / 60)) / (1 - 0.5 ** (1 / 7))

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        out: dict[int, float | None] = {}
        for p in ctx.pool:
            if not p.wiki_views_short or not p.wiki_views_recent:
                out[p.player_id] = None
                continue
            ratio = p.wiki_views_short / max(p.wiki_views_recent * self._STEADY, 1)
            out[p.player_id] = math.log10(max(ratio, 0.01))
        return out


class TeamStrengthFactor(Factor):
    """Winning matters: the team's win% in games the player appeared in."""

    name, label = "team", "Team"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        return {p.player_id: p.team_win_pct for p in ctx.pool}


class TeamDirectionFactor(Factor):
    """Where the franchise is headed, not just where it is: current win%
    plus a youth adjustment (a 45-win team with a 24-year-old core is worth
    more than a 45-win team of 33-year-olds). Team age is minutes-weighted."""

    name, label = "team_direction", "Dir"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        team_age: dict[str, float] = {}
        for team, roster in ctx.by_team.items():
            total_min = sum(q.minutes * q.games_played for q in roster) or 1
            team_age[team] = sum(
                q.age * q.minutes * q.games_played for q in roster
            ) / total_min
        out: dict[int, float | None] = {}
        for p in ctx.pool:
            age = team_age.get(p.team_abbr, 26.5)
            youth = max(0.0, 26.5 - age) * 0.03 - max(0.0, age - 28.0) * 0.03
            out[p.player_id] = p.team_win_pct + youth
        return out


class TeammateQualityFactor(Factor):
    """The supporting cast: minutes-weighted average Game Score of the
    player's teammates. Better teammates = more wins, more spotlight,
    deeper playoff runs."""

    name, label = "teammates", "Cast"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        out: dict[int, float | None] = {}
        for p in ctx.pool:
            mates = [q for q in ctx.by_team.get(p.team_abbr, []) if q.player_id != p.player_id]
            if not mates:
                out[p.player_id] = None
                continue
            total_min = sum(q.minutes * q.games_played for q in mates) or 1
            out[p.player_id] = sum(
                game_score(q) * q.minutes * q.games_played for q in mates
            ) / total_min
        return out


# ------------------------------------------------------------- sentiment

class SentimentProvider(ABC):
    """Pluggable social-sentiment source. Implement `scores` returning a
    per-player sentiment level (positive = bullish chatter) and assign an
    instance to SENTIMENT_PROVIDER. Planned implementations: Reddit r/nba
    comment sentiment (free API), Bluesky firehose, X/Twitter (paid)."""

    @abstractmethod
    def scores(self, ctx: MarketContext) -> dict[int, float | None]: ...


class NullSentiment(SentimentProvider):
    """No sentiment source wired yet — every player gets the pool median."""

    def scores(self, ctx: MarketContext) -> dict[int, float | None]:
        return {}


SENTIMENT_PROVIDER: SentimentProvider = NullSentiment()


class SentimentFactor(Factor):
    name, label = "sentiment", "Buzz"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        scores = SENTIMENT_PROVIDER.scores(ctx)
        return {p.player_id: scores.get(p.player_id) for p in ctx.pool}


class MatchupFactor(Factor):
    """In-season: opponent-adjusted recent performance (production against
    good defenses counts extra; head-to-head history vs tonight's opponent).
    Needs per-game logs — inert until those land (weight is 0 in the
    offseason anyway). See MODEL.md."""

    name, label = "matchup", "H2H"

    def raw(self, ctx: MarketContext) -> dict[int, float | None]:
        return {p.player_id: None for p in ctx.pool}


FACTORS: list[Factor] = [
    PerformanceFactor(),
    ProjectionFactor(),
    PopularityFactor(),
    MomentumFactor(),
    TeamStrengthFactor(),
    TeamDirectionFactor(),
    TeammateQualityFactor(),
    SentimentFactor(),
    MatchupFactor(),
]


# ------------------------------------------------------------- engine

def _zscores(values: list[float]) -> list[float]:
    n = len(values)
    if n < 2:
        return [0.0] * n
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    return [0.0] * n if std == 0 else [(v - mean) / std for v in values]


def compute(pool: list[PlayerInputs], phase: str | None = None) -> tuple[dict[int, float], dict[int, dict[str, float]]]:
    """(player_id -> composite, player_id -> {factor_name: z}). Missing raw
    scores take the pool median before z-scoring, so a factor that can't
    assess a player neither helps nor hurts them."""
    phase = phase or current_phase()
    ctx = MarketContext(pool=pool, phase=phase)

    composites = {p.player_id: 0.0 for p in pool}
    breakdown: dict[int, dict[str, float]] = {p.player_id: {} for p in pool}

    for factor in FACTORS:
        weight = WEIGHTS[factor.name][phase]
        raw = factor.raw(ctx)
        known = sorted(v for v in raw.values() if v is not None)
        median = known[len(known) // 2] if known else 0.0
        filled = [raw.get(p.player_id) if raw.get(p.player_id) is not None else median for p in pool]
        zs = _zscores(filled)
        for p, z in zip(pool, zs):
            breakdown[p.player_id][factor.name] = round(z, 4)
            composites[p.player_id] += weight * z

    return composites, breakdown
