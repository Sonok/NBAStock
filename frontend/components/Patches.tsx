"use client";

import type { Badge } from "@/lib/api";

// Varsity letterman patches. Three tiers of prestige:
//   gold   — won the award / All-Star (chenille gold)
//   silver — All-NBA / All-Defense teams
//   felt   — awards-ballot appearances (quiet felt patch)
// The dashed inner border is the stitching; alternating rotation makes them
// read as sewn on, not printed.
const TIER_STYLE: Record<Badge["tier"], { outer: string; inner: string }> = {
  gold: {
    outer: "linear-gradient(160deg, #e7c766 0%, #c49a2e 45%, #8f6d1c 100%)",
    inner: "rgba(40, 28, 4, 0.85)",
  },
  silver: {
    outer: "linear-gradient(160deg, #d9d9d9 0%, #a8a8a8 45%, #6f6f6f 100%)",
    inner: "rgba(20, 20, 20, 0.85)",
  },
  felt: {
    outer: "linear-gradient(160deg, #3a3a38 0%, #262624 100%)",
    inner: "rgba(255, 255, 255, 0.75)",
  },
};

export default function Patches({ badges }: { badges: Badge[] }) {
  if (!badges.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {badges.map((b, i) => {
        const s = TIER_STYLE[b.tier];
        return (
          <span
            key={`${b.code}-${b.label}`}
            className={`inline-block rounded-lg p-[3px] shadow-[0_3px_8px_rgba(0,0,0,0.45)] transition-transform duration-200 hover:rotate-0 hover:scale-105 ${
              i % 2 === 0 ? "-rotate-[1.6deg]" : "rotate-[1.3deg]"
            }`}
            style={{ background: s.outer }}
            title={b.label}
          >
            <span
              className="block rounded-md border border-dashed px-2.5 py-1 text-[11px] font-black uppercase tracking-widest"
              style={{
                borderColor: s.inner,
                color: b.tier === "felt" ? "var(--text-secondary)" : s.inner,
              }}
            >
              {b.label}
            </span>
          </span>
        );
      })}
    </div>
  );
}
