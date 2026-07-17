# The NBAStock Pricing Model

**v0.4 — multi-factor, phase-weighted, extensible.**

```
composite(p) = Σ_f  w_f(phase) · z_f(p)          over factors f
price(p)     = $30 · e^(0.85 · composite(p))     clamped to [$1, $1500]
```

Every factor is z-scored across the ~400 qualified players (15+ games,
12+ min/game), so the model is self-calibrating: a price expresses how many
standard deviations a player sits from league average on each dimension,
compounded exponentially — markets price stars superlinearly.

## The factors (`backend/app/factors.py`)

Each is a `Factor` subclass; the engine z-scores its raw output and applies
the phase weight. Players a factor can't assess get the pool median (no
penalty for missing data).

| Factor | What it measures | Raw signal |
|---|---|---|
| **Performance** | On-court production | Hollinger Game Score from per-game box stats |
| **Projection** | How good they're *going* to be | Game Score × NBA aging curve (≤21: +10%, 22–23: +6%, 24–25: +3%, 26–28: flat, 29–30: −3%, 31–33: −6%, 34+: −10%) |
| **Popularity** | Real-world attention | log₁₀ of exponentially decayed Wikipedia pageviews (60-day half-life) + star-power blend |
| **Momentum** | "On a roll" | log ratio of 7-day-decay to 60-day-decay attention vs the steady state — positive when attention is accelerating |
| **Team** | Winning matters | Team win% in the player's games |
| **Team direction** | Where the franchise is headed | Win% ± youth adjustment from minutes-weighted roster age (young winners ascend, old winners age out) |
| **Teammates** | The supporting cast | Minutes-weighted average Game Score of teammates |
| **Sentiment** | What people are saying | Pluggable `SentimentProvider` ABC — null today; Reddit/Bluesky/X providers drop in without touching the engine |
| **Matchup** | Head-to-head / opponent-adjusted form | Inert until per-game logs land (in-season) |

## Season-phase weights

The market breathes with the calendar. Offseason prices are deliberately
stagnant — the volatile factors are damped and slow-moving fundamentals
(projection, team direction) matter more:

| Factor | Offseason | Regular | Playoffs |
|---|---:|---:|---:|
| Performance | .42 | .40 | .42 |
| Projection | .15 | .08 | .05 |
| Popularity | .12 | .18 | .20 |
| Momentum | .04 | .10 | .12 |
| Team | .10 | .08 | .08 |
| Team direction | .08 | .04 | .02 |
| Teammates | .05 | .04 | .04 |
| Sentiment | .04 | .05 | .05 |
| Matchup | .00 | .03 | .02 |

Phases by month: Jul–Sep offseason, Oct–Mar regular, Apr–Jun playoffs.

## Attention dynamics

Attention is a **decaying stock, not a window** (`S_t = S_{t−1}·λ + views_t`,
half-life 60 days). Windows create cliffs — a Finals run sliding out of a
30-day window read as a 13% crash; under decay it fades gently while new
spikes still price in immediately. The 7-day twin of the same recursion
powers the momentum factor.

## Extension points (built, waiting for data)

- **`SentimentProvider`** — implement `.scores(ctx)` and assign to
  `factors.SENTIMENT_PROVIDER`. Planned: Reddit r/nba comment sentiment
  (free API + VADER or Claude Haiku ≈ $50–90/mo), Bluesky firehose (free),
  X/Twitter pay-per-use (gated by the signals system to control cost).
- **`MatchupFactor`** — per-game logs unlock opponent-adjusted production,
  head-to-head history, and strength-of-schedule weighting.
- **Live intraday pricing** — the play-by-play collector already streams
  game moments; an in-game performance delta can tick prices during games.

## Ideas backlog (not yet built)

- **Learned projection** — replace the hand-tuned aging curve with a model
  fit on historical career arcs (gradient boosting over age/role/usage);
  rookies get wider uncertainty, priced like high-vol options.
- **Injury discount** — availability risk factor from news-feed injury
  signals (games missed rate × recency).
- **Contract-year effect** — well-documented production bump; needs salary
  data (spotrac/bbref contracts).
- **Playoff leverage** — team's playoff odds amplify star prices late season.
- **ELO-style team momentum** — rolling team form beyond season win%.
- **Usage vacuum** — teammate injury/departure redistributes touches;
  detect roster changes and boost remaining ball-handlers.
- **Market microstructure** — once user liquidity exists, let order flow
  move prices around the model's fair value (model = market maker's mid).
- **Uncertainty bands** — publish a confidence interval per price (rookies
  and low-minute players get wide bands; UI can show them).

## Honest limitations

- Offseason performance data is frozen (last season's stats) — performance
  z-scores only move on roster/qualification changes until October.
- Wikipedia attention proxies fame, not sentiment — a scandal and a title
  run both spike views. The sentiment factor exists to separate them.
- The aging curve is a population average; it knows nothing about a
  specific player's injury history or role change.
