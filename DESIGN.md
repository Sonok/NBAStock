# NBAStock Design System

The product should feel like a **premium trading floor for basketball**:
dark, fast, confident. Two design languages meet on every screen — sports
card culture (team colors, cutouts, foil) and financial UI (tickers,
sparklines, green/red deltas) — and each has strict lanes so they never
fight.

## Brand personality

- **Dark by default.** One theme. The product is an evening product.
- **The data is the only loud thing.** Chrome is recessive; prices, deltas,
  and team-color banners carry all the energy.
- **Sports-card collectibility.** Tiers read as rarity (foil > silver >
  hairline), cutout players rise out of team-color banners like a 1990
  Skybox set.

## Color tokens

Defined once in `frontend/app/globals.css` as CSS custom properties.

| Token | Value | Role |
|---|---|---|
| `--page` | `#0d0d0d` | page plane (plus faint blue/red radial washes) |
| `--surface-1` | `#1a1a19` | cards, nav, inputs, modals |
| `--text-primary` | `#ffffff` | headline ink |
| `--text-secondary` | `#c3c2b7` | supporting ink |
| `--text-muted` | `#898781` | labels, axis text |
| `--gridline` | `#2c2c2a` | hairlines inside charts |
| `--baseline` | `#383835` | chart baselines, scrollbar |
| `--border-hairline` | `rgba(255,255,255,0.10)` | card/nav borders |
| `--series-pos` | `#3987e5` | positive z-score bars (cool pole) |
| `--series-neg` | `#e66767` | negative z-score bars (warm pole) |
| `--delta-good` | `#0ca30c` | price up, LONG, buy |
| `--delta-bad` | `#d03b3b` | price down, SHORT, sell |

### The three color lanes (never cross them)

1. **Team colors** (`frontend/lib/teamColors.ts`) — *brand identity only*:
   card banners, hover glow. Never used to encode data. Team **logos are
   trademarked and never appear**; colors are safe.
2. **Data colors** — the diverging blue/red pair for z-score bars, ordinal
   blue steps for tier dots, muted gray for sparkline history with a blue
   accent dot on "now". Assigned by the data's job, validated for
   colorblind separation on the dark surface.
3. **Money colors** — green/red *only* for direction of money (price
   change, P/L, long/short, buy/sell). Never decorative.

**Text never wears a data or team color** — values and labels stay in text
tokens; a colored mark beside the text carries the meaning. (Exception:
white type on banner gradients, which sit behind a black scrim for
contrast.)

## The player card (the brand unit)

```
┌───────────────────────────────┐  ← foil border by tier:
│ TEAM #rank            ● S     │    S = gold holo gradient
│  (team-color duotone gradient │    A = silver gradient
│   + halftone dots, fading →)  │    B/C/D = 1px hairline
│ FIRSTNAME            ▟██▙     │
│ LASTNAME (bold caps) ████ ←cutout headshot,
├───────────────────────▀▀──────┤   object-bottom, drop shadow
│ $278.62            ~~~~~~•    │ ← price + 30d sparkline
│ ▼ 0.2% 30d                    │
│ PERF  ────────▮▮▮▮  +4.1      │ ← diverging bars from center
│ POP   ────────▮▮    +1.8      │   blue right = above league avg
│ TEAM  ────────▮     +1.1      │   red left  = below
│ [   Buy   ] [   Sell   ]      │
│ 27.7   12.9   10.7   66       │
│ PPG    RPG    APG    WIN%     │
└───────────────────────────────┘
```

Rules: banner gradient = team primary → near-black at 150°, secondary color
as a faint radial accent; halftone dots mask out toward the cutout; last
name auto-shrinks past 9/13 chars rather than truncating; hover = ‑2px lift
+ team-color glow shadow (200ms).

## Typography

Geist Sans everywhere (system-ui fallback). No serif or display face.

- Player last name: extrabold, uppercase, tight tracking (the "jersey" type)
- Prices: semibold, proportional figures
- Tables/tickers: `tabular-nums` so columns align
- Labels: 10px uppercase, wide tracking, muted ink

## Motion

- Card hover: lift + glow, 150–200ms ease. Nothing else on the grid moves.
- Ticker tape: 90s linear loop, pauses on hover, honors
  `prefers-reduced-motion`.
- No entrance animations, no parallax, no springs — "fast" reads as
  restraint, not choreography.

## Chart rules (from the dataviz method)

- Breakdown bars: 6px tall, 4px rounded data-end, grow from a center
  baseline; diverging blue/red; values clamped to ±3σ.
- Sparkline: 30 points, 1.5px muted line, current value = blue dot with a
  2px surface ring; no axes (the price + delta text carry the numbers).
- One axis per chart, always. Sequential = one hue light→dark.
  Tier = ordinal steps of one blue ramp, never five different hues.

## Voice

Market language, plainly: "Top gainer", "▼ 8.6% 30d", "LONG/SHORT",
"Join · get $10k". Footer always carries: *Virtual market — not real
securities.*
