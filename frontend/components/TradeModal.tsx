"use client";

import { useState } from "react";
import { executeTrade, type Player } from "@/lib/api";
import { getUsername, notifyRefresh } from "@/lib/user";

export default function TradeModal({
  player,
  action,
  onClose,
}: {
  player: Player;
  action: "buy" | "sell";
  onClose: () => void;
}) {
  const [shares, setShares] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const username = getUsername();
  const total = shares * player.price;

  async function submit() {
    if (!username || shares <= 0) return;
    setBusy(true);
    setError(null);
    try {
      const r = await executeTrade({ username, player_id: player.player_id, shares, action });
      setDone(
        `${action === "buy" ? "Bought" : "Sold"} ${shares} @ $${r.executed_price.toFixed(2)} — cash $${r.cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
      );
      notifyRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Trade failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-1)] p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-sm text-[var(--text-secondary)]">
          {action === "buy" ? "Buy" : "Sell / short"}
        </p>
        <p className="mt-0.5 text-lg font-semibold">{player.name}</p>
        <p className="text-sm text-[var(--text-muted)]">
          {player.team_abbr} · ${player.price.toFixed(2)} per share
        </p>

        {!username && (
          <p className="mt-4 text-sm text-[var(--delta-bad)]">
            Pick a username in the top bar first — you get $10,000 to start.
          </p>
        )}

        {username && !done && (
          <>
            <label className="mt-4 block text-xs uppercase tracking-wide text-[var(--text-muted)]">
              Shares
            </label>
            <input
              type="number"
              min={1}
              step={1}
              value={shares}
              onChange={(e) => setShares(Math.max(0, Number(e.target.value)))}
              className="mt-1 w-full rounded-lg border border-[var(--border-hairline)] bg-[var(--page)] px-3 py-2 text-lg tabular-nums text-[var(--text-primary)] outline-none focus:border-[rgba(255,255,255,0.3)]"
            />
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-[var(--text-secondary)]">
                {action === "buy" ? "Total cost" : "Total proceeds"}
              </span>
              <span className="font-semibold tabular-nums">
                ${total.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
            </div>
            {error && <p className="mt-3 text-sm text-[var(--delta-bad)]">{error}</p>}
            <button
              onClick={submit}
              disabled={busy || shares <= 0}
              className={`mt-4 w-full rounded-lg py-2.5 font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50 ${
                action === "buy" ? "bg-[var(--delta-good)]" : "bg-[var(--delta-bad)]"
              }`}
            >
              {busy ? "Executing…" : action === "buy" ? `Buy ${shares}` : `Sell ${shares}`}
            </button>
          </>
        )}

        {done && (
          <div className="mt-4">
            <p className="text-sm text-[var(--delta-good)]">{done}</p>
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-lg border border-[var(--border-hairline)] py-2.5 font-medium text-[var(--text-primary)] hover:bg-[var(--page)]"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
