"use client";

import { useEffect, useState } from "react";
import { fetchPlayers, type Player } from "@/lib/api";

// Exchange-style tape: biggest 30-day movers, scrolling continuously.
export default function Ticker() {
  const [movers, setMovers] = useState<Player[]>([]);

  useEffect(() => {
    fetchPlayers({ limit: 400 })
      .then((d) => {
        const ranked = [...d.players].sort(
          (a, b) => Math.abs(b.change_30d_pct) - Math.abs(a.change_30d_pct)
        );
        setMovers(ranked.slice(0, 28));
      })
      .catch(() => setMovers([]));
  }, []);

  if (movers.length === 0) return null;

  const items = [...movers, ...movers]; // duplicated for a seamless loop
  return (
    <div className="ticker border-b border-[var(--border-hairline)] bg-[rgba(22,24,27,0.6)]">
      <div className="ticker-track items-center gap-8 py-1.5">
        {items.map((p, i) => {
          const up = p.change_30d_pct >= 0;
          const last = p.name.split(" ").slice(1).join(" ") || p.name;
          return (
            <span key={`${p.player_id}-${i}`} className="flex items-center gap-2 text-xs whitespace-nowrap">
              <span className="font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                {last}
              </span>
              <span className="tabular-nums text-[var(--text-primary)]">
                ${p.price.toFixed(2)}
              </span>
              <span
                className="font-medium tabular-nums"
                style={{ color: up ? "var(--delta-good)" : "var(--delta-bad)" }}
              >
                {up ? "▲" : "▼"}{Math.abs(p.change_30d_pct).toFixed(1)}%
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
