"use client";

import { useEffect, useState } from "react";
import { fetchLeaderboard, type LeaderboardRow } from "@/lib/api";
import { getUsername } from "@/lib/user";

export default function LeaderboardPage() {
  const [rows, setRows] = useState<LeaderboardRow[]>([]);
  const me = typeof window !== "undefined" ? getUsername() : null;

  useEffect(() => {
    fetchLeaderboard()
      .then((d) => setRows(d.leaderboard))
      .catch(() => setRows([]));
  }, []);

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-3xl font-semibold">Leaderboard</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Ranked by total equity — everyone starts with $10,000.
      </p>

      <div className="mt-6 overflow-hidden rounded-xl border border-[var(--border-hairline)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-hairline)] text-left text-xs uppercase tracking-wide text-[var(--text-muted)]">
              <th className="px-4 py-3 font-medium">#</th>
              <th className="px-4 py-3 font-medium">Trader</th>
              <th className="px-4 py-3 text-right font-medium">Equity</th>
              <th className="px-4 py-3 text-right font-medium">Return</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {rows.map((r) => (
              <tr
                key={r.username}
                className={`border-b border-[var(--border-hairline)] last:border-0 ${
                  r.username === me ? "bg-[var(--surface-1)]" : ""
                }`}
              >
                <td className="px-4 py-2.5 text-[var(--text-muted)]">{r.rank}</td>
                <td className="px-4 py-2.5 font-medium">
                  @{r.username}
                  {r.username === me && (
                    <span className="ml-2 text-xs text-[var(--text-muted)]">you</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  ${r.equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </td>
                <td
                  className="px-4 py-2.5 text-right font-medium"
                  style={{
                    color: r.total_return_pct >= 0 ? "var(--delta-good)" : "var(--delta-bad)",
                  }}
                >
                  {r.total_return_pct >= 0 ? "+" : ""}
                  {r.total_return_pct.toFixed(2)}%
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-[var(--text-muted)]">
                  No traders yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
