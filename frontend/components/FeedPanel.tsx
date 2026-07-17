"use client";

import { useEffect, useState } from "react";
import { fetchFeed, type MarketEvent } from "@/lib/api";

const POLL_MS = 20_000;

// type -> dot color (identity, not data): news gray, signals blue, plays amber
const DOT: Record<string, string> = {
  news: "var(--text-muted)",
  signal: "var(--series-pos)",
  play: "#c98500",
};

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function SignalBody({ e }: { e: MarketEvent }) {
  // roster moves get real typography instead of the raw message string
  const move = e.message.match(/^Roster move: (.+) → (\S+) \(from (\S+)\)$/);
  if (move) {
    return (
      <p className="text-[13px] leading-snug">
        <span className="font-semibold text-[var(--text-primary)]">{move[1]}</span>{" "}
        <span className="text-[var(--text-secondary)]">signs with</span>{" "}
        <span className="font-semibold text-[var(--text-primary)]">{move[2]}</span>{" "}
        <span className="text-[var(--text-muted)]">· leaves {move[3]}</span>
      </p>
    );
  }
  // detector messages: keep the substance, drop the boilerplate
  const text = e.message
    .replace(" — market watching", "")
    .replace(/^In the news: /, "");
  return <p className="text-[13px] leading-snug text-[var(--text-secondary)]">{text}</p>;
}

function EventRow({ e }: { e: MarketEvent }) {
  return (
    <li className="flex items-start gap-2.5 py-2.5 [&:not(:last-child)]:border-b [&:not(:last-child)]:border-[rgba(255,255,255,0.05)]">
      <span
        className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: DOT[e.type] ?? "var(--text-muted)" }}
      />
      <div className="min-w-0 flex-1">
        {e.type === "news" ? (
          e.url ? (
            <a
              href={e.url}
              target="_blank"
              rel="noreferrer"
              className="block text-[13px] leading-snug text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
            >
              {e.message}
            </a>
          ) : (
            <p className="text-[13px] leading-snug text-[var(--text-secondary)]">{e.message}</p>
          )
        ) : e.type === "play" ? (
          <p className="text-[13px] leading-snug text-[var(--text-secondary)]">
            <span className="font-semibold text-[var(--text-primary)]">{e.name}</span>{" "}
            {e.message.replace(/^[A-Za-z- ]+: /, "")}
          </p>
        ) : (
          <SignalBody e={e} />
        )}
      </div>
      <span className="shrink-0 pt-[3px] text-[10px] tabular-nums text-[var(--text-muted)]">
        {timeAgo(e.ts)}
      </span>
    </li>
  );
}

export default function FeedPanel({
  playerId,
  title = "The Wire",
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
    <div className="panel p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
          {title}
        </h2>
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--delta-good)] opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--delta-good)]" />
        </span>
      </div>
      {events.length === 0 ? (
        <p className="mt-3 text-[13px] text-[var(--text-muted)]">
          Quiet {playerId ? "for this player" : "market"} — headlines, roster moves, and live
          plays land here.
        </p>
      ) : (
        // Scrolls internally (capped below viewport height) so the sticky
        // rail never outgrows the screen; overscroll-contain keeps the list
        // scroll from chaining into the page.
        <div className="mt-1.5 max-h-[calc(100vh-14rem)] overflow-y-auto overscroll-contain pr-1 [mask-image:linear-gradient(to_bottom,black_calc(100%-20px),transparent)]">
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
