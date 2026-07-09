"use client";

import type { ShotZone } from "@/lib/api";

// Half-court hot zones: concentric distance bands from the hoop, colored by
// FG% on the sequential blue ramp (dark-surface ordinal steps). The court
// carries color; the list beside it carries the exact numbers.
const ZONE_LABEL: Record<string, string> = {
  "0-3": "At the rim (0–3 ft)",
  "3-10": "Paint (3–10 ft)",
  "10-16": "Mid-range (10–16 ft)",
  "16-3P": "Long two (16 ft–3P)",
  "3P": "Three-point",
};

// distance ft -> px (3P arc ≈ 23.75 ft)
const HOOP = { x: 250, y: 42 };
const FT = 9.2;
const BAND_R: Record<string, number> = {
  "0-3": 3 * FT + 14,
  "3-10": 10 * FT,
  "10-16": 16 * FT,
  "16-3P": 23.75 * FT,
};

function fgColor(pct: number): string {
  if (pct < 0.35) return "#184f95";
  if (pct < 0.45) return "#256abf";
  if (pct < 0.55) return "#3987e5";
  if (pct < 0.65) return "#6da7ec";
  return "#9ec5f4";
}

export default function ShotZones({ zones }: { zones: ShotZone[] }) {
  if (!zones.length) return null;
  const byZone = Object.fromEntries(zones.map((z) => [z.zone, z]));
  // paint outermost band first, then cover with the inner ones
  const order = ["3P", "16-3P", "10-16", "3-10", "0-3"];

  return (
    <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
      <svg viewBox="0 0 500 290" className="w-full max-w-[380px] shrink-0 rounded-lg">
        <rect x="0" y="0" width="500" height="290" fill="var(--page)" />
        {order.map((key) => {
          const z = byZone[key];
          if (!z) return null;
          const r = key === "3P" ? 900 : BAND_R[key];
          return (
            <circle
              key={key}
              cx={HOOP.x}
              cy={HOOP.y}
              r={r}
              fill={fgColor(z.fg_pct)}
              opacity="0.9"
            >
              <title>{`${ZONE_LABEL[key]}: ${(z.fg_pct * 100).toFixed(0)}% FG`}</title>
            </circle>
          );
        })}
        {/* court chrome: baseline, lane, arc, hoop */}
        <line x1="0" y1="2" x2="500" y2="2" stroke="rgba(255,255,255,0.35)" strokeWidth="3" />
        <rect x="180" y="2" width="140" height="155" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="2" />
        <path
          d={`M ${HOOP.x - 23.75 * FT} 2 A ${23.75 * FT} ${23.75 * FT} 0 0 0 ${HOOP.x + 23.75 * FT} 2`}
          fill="none"
          stroke="rgba(255,255,255,0.35)"
          strokeWidth="2"
        />
        <circle cx={HOOP.x} cy={HOOP.y} r="8" fill="none" stroke="#ffffff" strokeWidth="3" />
      </svg>

      <ul className="w-full space-y-2">
        {["0-3", "3-10", "10-16", "16-3P", "3P"].map((key) => {
          const z = byZone[key];
          if (!z) return null;
          return (
            <li key={key} className="flex items-center gap-2.5 text-sm">
              <span
                className="h-3 w-3 shrink-0 rounded-sm"
                style={{ background: fgColor(z.fg_pct) }}
              />
              <span className="flex-1 text-[var(--text-secondary)]">{ZONE_LABEL[key]}</span>
              <span className="font-semibold tabular-nums">{(z.fg_pct * 100).toFixed(0)}%</span>
              <span className="w-20 text-right text-xs tabular-nums text-[var(--text-muted)]">
                {(z.share * 100).toFixed(0)}% of shots
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
