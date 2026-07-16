"use client";

import { useCallback, useEffect, useState } from "react";
import { API_BASE, fetchPortfolio, type Portfolio } from "@/lib/api";
import { getUsername, REFRESH_EVENT } from "@/lib/user";

function money(v: number) {
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

function Tile({ label, value, delta }: { label: string; value: string; delta?: number }) {
  return (
    <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
      <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {delta !== undefined && (
        <p
          className="mt-0.5 text-sm font-medium"
          style={{ color: delta >= 0 ? "var(--delta-good)" : "var(--delta-bad)" }}
        >
          {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}% all time
        </p>
      )}
    </div>
  );
}

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [user, setUser] = useState<string | null>(null);

  const refresh = useCallback(() => {
    const u = getUsername();
    setUser(u);
    if (u) fetchPortfolio().then(setPortfolio).catch(() => setPortfolio(null));
    else setPortfolio(null);
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(REFRESH_EVENT, refresh);
    return () => window.removeEventListener(REFRESH_EVENT, refresh);
  }, [refresh]);

  if (!user) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-16 text-center text-[var(--text-secondary)]">
        Sign in from the top bar to start trading — every new account gets $10,000.
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <h1 className="text-3xl font-semibold">Portfolio</h1>
      {portfolio && (
        <>
          <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Tile
              label="Equity"
              value={money(portfolio.equity)}
              delta={portfolio.total_return_pct}
            />
            <Tile label="Cash" value={money(portfolio.cash)} />
            <Tile label="Positions value" value={money(portfolio.market_value)} />
          </div>

          {portfolio.holdings.length === 0 ? (
            <p className="mt-10 text-sm text-[var(--text-muted)]">
              No positions yet — head to the Market and buy (or short) someone.
            </p>
          ) : (
            <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border-hairline)]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border-hairline)] text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">
                    <th className="px-4 py-3 font-medium">Player</th>
                    <th className="px-4 py-3 text-right font-medium">Side</th>
                    <th className="px-4 py-3 text-right font-medium">Shares</th>
                    <th className="px-4 py-3 text-right font-medium">Avg cost</th>
                    <th className="px-4 py-3 text-right font-medium">Price</th>
                    <th className="px-4 py-3 text-right font-medium">Value</th>
                    <th className="px-4 py-3 text-right font-medium">Unrealized P/L</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {portfolio.holdings.map((h) => (
                    <tr key={h.player_id} className="border-b border-[var(--border-hairline)] last:border-0">
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={`${API_BASE}${h.headshot}`}
                            alt=""
                            className="h-8 w-8 rounded-full bg-[var(--gridline)] object-cover object-top"
                          />
                          <div>
                            <p className="font-medium text-[var(--text-primary)]">{h.name}</p>
                            <p className="text-xs text-[var(--text-muted)]">{h.team_abbr}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <span
                          className="rounded-full px-2 py-0.5 text-xs font-semibold"
                          style={{
                            color: h.shares >= 0 ? "var(--delta-good)" : "var(--delta-bad)",
                            background: h.shares >= 0 ? "rgba(12,163,12,0.12)" : "rgba(208,59,59,0.12)",
                          }}
                        >
                          {h.shares >= 0 ? "LONG" : "SHORT"}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right">{Math.abs(h.shares)}</td>
                      <td className="px-4 py-2.5 text-right">{money(h.avg_cost)}</td>
                      <td className="px-4 py-2.5 text-right">{money(h.price)}</td>
                      <td className="px-4 py-2.5 text-right">{money(h.market_value)}</td>
                      <td
                        className="px-4 py-2.5 text-right font-medium"
                        style={{
                          color: h.unrealized_pl >= 0 ? "var(--delta-good)" : "var(--delta-bad)",
                        }}
                      >
                        {h.unrealized_pl >= 0 ? "+" : ""}
                        {money(h.unrealized_pl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}
