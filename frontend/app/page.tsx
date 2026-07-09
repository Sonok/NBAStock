"use client";

import { useEffect, useState } from "react";
import PlayerCard from "@/components/PlayerCard";
import { fetchPlayers, type PlayersResponse } from "@/lib/api";

export default function MarketPage() {
  const [search, setSearch] = useState("");
  const [data, setData] = useState<PlayersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true);
      fetchPlayers({ limit: 60, search })
        .then((d) => {
          setData(d);
          setError(null);
        })
        .catch(() => setError("Can't reach the NBAStock API — is the backend running on port 8000?"))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  const gainer = data
    ? [...data.players].sort((a, b) => b.change_30d_pct - a.change_30d_pct)[0]
    : null;
  const loser = data
    ? [...data.players].sort((a, b) => a.change_30d_pct - b.change_30d_pct)[0]
    : null;
  const famous = data
    ? [...data.players].sort((a, b) => (b.wiki_views ?? 0) - (a.wiki_views ?? 0))[0]
    : null;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="bg-gradient-to-r from-white via-white to-[var(--text-muted)] bg-clip-text text-4xl font-extrabold tracking-tight text-transparent">
            The Market
          </h1>
          <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
            {data ? `${data.count} players priced` : "Player prices"} · {data?.season ?? "2025-26"} season ·
            driven by performance, popularity, and team strength
          </p>
        </div>
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search players…"
          className="w-64 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[rgba(255,255,255,0.3)]"
        />
      </header>

      {data && !search && gainer && loser && famous && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            {
              label: "Top gainer · 30d",
              player: gainer,
              stat: `▲ ${gainer.change_30d_pct.toFixed(1)}%`,
              color: "var(--delta-good)",
            },
            {
              label: "Top loser · 30d",
              player: loser,
              stat: `▼ ${Math.abs(loser.change_30d_pct).toFixed(1)}%`,
              color: "var(--delta-bad)",
            },
            {
              label: "Most famous",
              player: famous,
              stat: `${((famous.wiki_views ?? 0) / 1e6).toFixed(1)}M views`,
              color: "var(--text-secondary)",
            },
          ].map((t) => (
            <div
              key={t.label}
              className="flex items-center justify-between rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-1)] px-4 py-3"
            >
              <div>
                <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{t.label}</p>
                <p className="mt-0.5 font-semibold text-[var(--text-primary)]">{t.player.name}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold tabular-nums" style={{ color: t.color }}>
                  {t.stat}
                </p>
                <p className="text-xs tabular-nums text-[var(--text-muted)]">
                  ${t.player.price.toFixed(2)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="mt-10 rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-1)] p-6 text-sm text-[var(--text-secondary)]">
          {error}
          <p className="mt-2 text-[var(--text-muted)]">
            cd backend && .venv/bin/uvicorn app.main:app --port 8000
          </p>
        </div>
      )}

      {loading && !data && !error && (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="h-56 animate-pulse rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-1)]"
            />
          ))}
        </div>
      )}

      {data && (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {data.players.map((p) => (
            <PlayerCard key={p.player_id} player={p} />
          ))}
        </div>
      )}

      {data && data.players.length === 0 && (
        <p className="mt-10 text-sm text-[var(--text-muted)]">No players match “{search}”.</p>
      )}

      <footer className="mt-10 border-t border-[var(--border-hairline)] pt-4 text-xs text-[var(--text-muted)]">
        Stats via Basketball-Reference · Prices from the NBAStock model v0 · Virtual market — not real
        securities
      </footer>
    </main>
  );
}
