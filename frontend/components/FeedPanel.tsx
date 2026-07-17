"use client";

import { useEffect, useState } from "react";
import { fetchFeed, type MarketEvent } from "@/lib/api";

const POLL_MS = 20_000;

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function EventRow({ e }: { e: MarketEvent }) {
  const body =
    e.type === "play" ? (
      <div className="min-w-0">
        <span className="mr-1.5 rounded border border-[#c98500] px-1 py-px text-[9px] font-bold uppercase tracking-widest text-[#c98500] align-middle">
          Live play
        </span>
        <span className="text-sm leading-snug text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--text-primary)]">{e.name}</span>{" "}
          — {e.message}
        </span>
      </div>
    ) : e.type === "signal" ? (
      <div className="min-w-0">
        <span className="mr-1.5 rounded border border-[var(--series-pos)] px-1 py-px text-[9px] font-bold uppercase tracking-widest text-[var(--series-pos)] align-middle">
          Notable
        </span>
        <span className="text-sm leading-snug text-[var(--text-secondary)]">{e.message}</span>
      </div>
    ) : e.type === "news" ? (
      <div className="min-w-0">
        <span className="mr-1.5 rounded bg-[var(--gridline)] px-1 py-px text-[9px] font-bold uppercase tracking-widest text-[var(--text-muted)] align-middle">
          News
        </span>
        {e.url ? (
          <a
            href={e.url}
            target="_blank"
            rel="noreferrer"
            className="text-sm leading-snug text-[var(--text-secondary)] underline-offset-2 hover:text-[var(--text-primary)] hover:underline"
          >
            {e.message}
          </a>
        ) : (
          <span className="text-sm leading-snug text-[var(--text-secondary)]">{e.message}</span>
        )}
      </div>
    ) : (
      <p className="min-w-0 text-sm leading-snug">
        <span className="font-semibold text-[var(--text-primary)]">{e.name}</span>{" "}
        <span
          className="font-medium tabular-nums"
          style={{
            color: (e.delta_pct ?? 0) >= 0 ? "var(--delta-good)" : "var(--delta-bad)",
          }}
        >
          {(e.delta_pct ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(e.delta_pct ?? 0).toFixed(1)}%
        </span>{" "}
        <span className="text-[var(--text-secondary)]">
          {e.message.replace(`${e.name} `, "").replace(/^[▲▼] [\d.]+% /, "")}
        </span>
      </p>
    );

  return (
    <li className="flex items-start justify-between gap-3 border-b border-[var(--border-hairline)] py-2.5 last:border-0">
      {body}
      <span className="shrink-0 pt-0.5 text-[10px] tabular-nums text-[var(--text-muted)]">
        {timeAgo(e.ts)}
      </span>
    </li>
  );
}

export default function FeedPanel({
  playerId,
  title = "Notable events",
}: {
  playerId?: number;
  title?: string;
}) {
  const [events, setEvents] = useState<MarketEvent[]>([]);

  useEffect(() => {
    const load = () => fetchFeed(playerId).then((d) => setEvents(d.events)).catch(() => {});
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [playerId]);

  return (
    <div className="rounded-xl border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--delta-good)] opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--delta-good)]" />
        </span>
        <h2 className="text-sm font-semibold uppercase tracking-wide">{title}</h2>
      </div>
      {events.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--text-muted)]">
          Quiet {playerId ? "for this player" : "market"} — price moves and headlines land here as
          they happen.
        </p>
      ) : (
        // Scrolls internally (capped below viewport height) so the sticky
        // rail never outgrows the screen; overscroll-contain keeps the list
        // scroll from chaining into the page.
        <div className="mt-2 max-h-[calc(100vh-14rem)] overflow-y-auto overscroll-contain pr-1 [mask-image:linear-gradient(to_bottom,black_calc(100%-20px),transparent)]">
          <ul className="pb-4">
            {events.slice(0, 20).map((e) => (
              <EventRow key={e.id} e={e} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
