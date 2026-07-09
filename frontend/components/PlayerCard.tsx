"use client";

import { useState } from "react";
import { API_BASE, type Player } from "@/lib/api";
import { teamColors } from "@/lib/teamColors";
import TradeModal from "@/components/TradeModal";

// Ordinal steps of the sequential blue ramp (dark-surface band) — tier is
// ordered data, so it wears one hue stepped by rank, not five hues.
const TIER_COLOR: Record<Player["tier"], string> = {
  S: "#9ec5f4",
  A: "#6da7ec",
  B: "#3987e5",
  C: "#256abf",
  D: "#184f95",
};

// "Foil" borders for the collectible tiers — a sports-card holo nod.
const TIER_BORDER: Partial<Record<Player["tier"], string>> = {
  S: "linear-gradient(135deg, #f6d365 0%, #fda085 25%, #9ec5f4 50%, #f6d365 75%, #fda085 100%)",
  A: "linear-gradient(135deg, #d7d7d7 0%, #8f8f8f 40%, #e8e8e8 60%, #9a9a9a 100%)",
};

const Z_RANGE = 3; // breakdown bars clamp z-scores to ±3

function Sparkline({ series }: { series: number[] }) {
  if (series.length < 2) return null;
  const w = 84;
  const h = 26;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const pts = series
    .map((v, i) => {
      const x = (i / (series.length - 1)) * (w - 6) + 3;
      const y = h - 4 - ((v - min) / span) * (h - 8);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const [lastX, lastY] = pts.split(" ").pop()!.split(",");
  return (
    <svg width={w} height={h} aria-hidden className="shrink-0">
      <polyline
        points={pts}
        fill="none"
        stroke="var(--text-muted)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* current value in the accent, ringed in surface so it reads on the line */}
      <circle cx={lastX} cy={lastY} r="3" fill="var(--series-pos)" stroke="var(--surface-1)" strokeWidth="2" />
    </svg>
  );
}

function BreakdownBar({ label, z }: { label: string; z: number }) {
  const clamped = Math.max(-Z_RANGE, Math.min(Z_RANGE, z));
  const pct = (Math.abs(clamped) / Z_RANGE) * 50;
  const positive = clamped >= 0;
  return (
    <div className="flex items-center gap-2" title={`${label}: ${z >= 0 ? "+" : ""}${z.toFixed(2)}σ vs league`}>
      <span className="w-10 text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </span>
      <div className="relative h-[6px] flex-1">
        <div className="absolute left-1/2 top-[-2px] h-[10px] w-px bg-[var(--baseline)]" />
        <div
          className="absolute top-0 h-full"
          style={{
            background: positive ? "var(--series-pos)" : "var(--series-neg)",
            left: positive ? "50%" : `${50 - pct}%`,
            width: `${pct}%`,
            borderRadius: positive ? "0 4px 4px 0" : "4px 0 0 4px",
          }}
        />
      </div>
      <span className="w-9 text-right text-[10px] tabular-nums text-[var(--text-secondary)]">
        {z >= 0 ? "+" : ""}
        {z.toFixed(1)}
      </span>
    </div>
  );
}

export default function PlayerCard({ player }: { player: Player }) {
  const [imgFailed, setImgFailed] = useState(false);
  const [trade, setTrade] = useState<"buy" | "sell" | null>(null);
  const colors = teamColors(player.team_abbr);
  const foil = TIER_BORDER[player.tier];
  const nameParts = player.name.split(" ");
  const lastName = nameParts.slice(1).join(" ") || nameParts[0];
  const firstName = nameParts.length > 1 ? nameParts[0] : "";
  const initials = nameParts.map((w) => w[0]).slice(0, 2).join("");

  const card = (
    <div className="group overflow-hidden rounded-xl bg-[var(--surface-1)] transition-transform duration-150 hover:-translate-y-0.5">
      {/* Team-color banner: duotone gradient + halftone texture, cutout on top */}
      <div
        className="relative h-28"
        style={{
          background: `radial-gradient(120% 160% at 85% -20%, ${colors.secondary}66 0%, transparent 50%), linear-gradient(150deg, ${colors.primary} 0%, ${colors.primary}dd 55%, #101010 130%)`,
        }}
      >
        {/* halftone dots, fading out toward the right */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: "radial-gradient(rgba(255,255,255,0.16) 1px, transparent 1px)",
            backgroundSize: "8px 8px",
            maskImage: "linear-gradient(105deg, black 20%, transparent 65%)",
            WebkitMaskImage: "linear-gradient(105deg, black 20%, transparent 65%)",
          }}
        />
        {/* darken the bottom of the banner so white type always clears it */}
        <div className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/55 to-transparent" />

        {/* cutout headshot, Skybox-style: no frame, rises from the banner floor */}
        <div className="absolute bottom-0 right-1 h-[104px] w-[142px]">
          {imgFailed ? (
            <div className="flex h-full w-full items-end justify-center pb-2 text-4xl font-bold text-white/25">
              {initials}
            </div>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={player.headshot.startsWith("http") ? player.headshot : `${API_BASE}${player.headshot}`}
              alt={player.name}
              className="h-full w-full object-contain object-bottom drop-shadow-[0_6px_10px_rgba(0,0,0,0.6)]"
              loading="lazy"
              onError={() => setImgFailed(true)}
            />
          )}
        </div>

        {/* identity block */}
        <div className="absolute bottom-2.5 left-4 right-[118px]">
          {firstName && (
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-white/75">
              {firstName}
            </p>
          )}
          <p
            className={`truncate font-extrabold uppercase leading-none text-white [text-shadow:0_1px_3px_rgba(0,0,0,0.5)] ${
              lastName.length > 13
                ? "text-sm tracking-normal"
                : lastName.length > 9
                  ? "text-base tracking-tight"
                  : "text-xl tracking-tight"
            }`}
          >
            {lastName}
          </p>
        </div>

        <div className="absolute left-4 top-3 flex items-center gap-2">
          <span className="rounded bg-black/35 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-widest text-white/90">
            {player.team_abbr}
          </span>
          <span className="text-[10px] font-medium text-white/70">#{player.rank}</span>
        </div>

        <span
          className="absolute right-3 top-3 flex items-center gap-1.5 rounded-full bg-black/40 px-2 py-0.5 text-xs font-bold text-white backdrop-blur-sm"
          title={`Tier ${player.tier}`}
        >
          <span className="h-2 w-2 rounded-full" style={{ background: TIER_COLOR[player.tier] }} />
          {player.tier}
        </span>
      </div>

      <div className="p-4 pt-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <p className="text-2xl font-semibold text-[var(--text-primary)]">
              ${player.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </p>
            <p
              className="mt-0.5 text-xs font-medium"
              style={{
                color:
                  player.change_30d_pct >= 0 ? "var(--delta-good)" : "var(--delta-bad)",
              }}
            >
              {player.change_30d_pct >= 0 ? "▲" : "▼"} {Math.abs(player.change_30d_pct).toFixed(1)}%
              <span className="ml-1 font-normal text-[var(--text-muted)]">30d</span>
            </p>
          </div>
          <Sparkline series={player.spark} />
        </div>

        <div className="mt-3 space-y-1.5">
          <BreakdownBar label="Perf" z={player.perf_z} />
          <BreakdownBar label="Pop" z={player.pop_z} />
          <BreakdownBar label="Team" z={player.team_z} />
        </div>

        <div className="mt-3 flex gap-2">
          <button
            onClick={() => setTrade("buy")}
            className="flex-1 rounded-lg bg-[var(--delta-good)] py-1.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          >
            Buy
          </button>
          <button
            onClick={() => setTrade("sell")}
            className="flex-1 rounded-lg border border-[var(--border-hairline)] py-1.5 text-sm font-semibold text-[var(--text-primary)] transition-colors hover:border-[var(--delta-bad)] hover:text-[var(--delta-bad)]"
          >
            Sell
          </button>
        </div>

        <div className="mt-3 grid grid-cols-4 gap-1 border-t border-[var(--border-hairline)] pt-2.5">
          {[
            ["PPG", player.stats.pts.toFixed(1)],
            ["RPG", player.stats.reb.toFixed(1)],
            ["APG", player.stats.ast.toFixed(1)],
            ["WIN%", `${Math.round(player.stats.team_win_pct * 100)}`],
          ].map(([label, value]) => (
            <div key={label} className="text-center">
              <p className="text-sm font-medium text-[var(--text-primary)]">{value}</p>
              <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  // Foil wrapper: gradient border via padding, hairline for common tiers.
  // Hover lights the card with its own team color.
  const glow = { "--glow": `${colors.primary}59` } as React.CSSProperties;
  const glowClass =
    "transition-shadow duration-200 hover:shadow-[0_16px_48px_-12px_var(--glow)]";
  return (
    <>
      {foil ? (
        <div className={`rounded-[13px] p-px ${glowClass}`} style={{ background: foil, ...glow }}>
          {card}
        </div>
      ) : (
        <div
          className={`rounded-[13px] border border-[var(--border-hairline)] ${glowClass}`}
          style={glow}
        >
          {card}
        </div>
      )}
      {trade && <TradeModal player={player} action={trade} onClose={() => setTrade(null)} />}
    </>
  );
}
