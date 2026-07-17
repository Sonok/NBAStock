"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import FeedPanel from "@/components/FeedPanel";
import Patches from "@/components/Patches";
import { BreakdownBar } from "@/components/PlayerCard";
import PriceChart from "@/components/PriceChart";
import Radar from "@/components/Radar";
import ShotZones from "@/components/ShotZones";
import TradeModal from "@/components/TradeModal";
import {
  API_BASE,
  fetchHistory,
  fetchPlayer,
  fetchProfile,
  type Player,
  type Profile,
} from "@/lib/api";
import { teamColors } from "@/lib/teamColors";

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const playerId = Number(id);
  const [player, setPlayer] = useState<Player | null>(null);
  const [history, setHistory] = useState<{ dates: string[]; prices: number[] } | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [trade, setTrade] = useState<"buy" | "sell" | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!playerId) return;
    fetchPlayer(playerId).then(setPlayer).catch(() => setError(true));
    fetchHistory(playerId).then(setHistory).catch(() => {});
    fetchProfile(playerId).then(setProfile).catch(() => {});
  }, [playerId]);

  if (error) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-16 text-center text-[var(--text-secondary)]">
        Player not found.{" "}
        <Link href="/" className="text-[var(--series-pos)] hover:underline">
          Back to the market
        </Link>
      </main>
    );
  }
  if (!player) {
    return (
      <main className="mx-auto max-w-5xl px-4 py-8">
        <div className="h-64 animate-pulse rounded-2xl border border-[var(--border-hairline)] bg-[var(--surface-1)]" />
      </main>
    );
  }

  const colors = teamColors(player.team_abbr);
  const up = player.change_30d_pct >= 0;

  const SectionHeader = ({ label }: { label: string }) => (
    <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
      <span
        className="inline-block h-[3px] w-4 rounded-full"
        style={{ background: colors.primary === "#111111" || colors.primary === "#161616" ? colors.secondary : colors.primary }}
      />
      {label}
    </h2>
  );

  return (
    <div className="relative">
      {/* ambient team-color wash bleeding down from the hero */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[36rem]"
        style={{
          background: `radial-gradient(70% 28rem at 50% 0%, ${colors.primary}2e 0%, transparent 70%)`,
        }}
      />
      <main className="relative mx-auto max-w-5xl px-4 py-8">
      <Link
        href="/"
        className="group inline-flex items-center gap-1 text-sm text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)]"
      >
        <span className="transition-transform group-hover:-translate-x-0.5">←</span> Market
      </Link>

      {/* Letterman hero: team-color jacket, giant cutout, varsity type */}
      <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--border-hairline)]">
        <div
          className="shine relative h-64"
          style={{
            background: `radial-gradient(120% 170% at 85% -20%, ${colors.secondary}59 0%, transparent 50%), linear-gradient(150deg, ${colors.primary} 0%, ${colors.primary}dd 55%, #0a0b0d 135%)`,
          }}
        >
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: "radial-gradient(rgba(255,255,255,0.14) 1px, transparent 1px)",
              backgroundSize: "9px 9px",
              maskImage: "linear-gradient(105deg, black 25%, transparent 70%)",
              WebkitMaskImage: "linear-gradient(105deg, black 25%, transparent 70%)",
            }}
          />
          <div className="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-black/60 to-transparent" />

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={player.headshot.startsWith("http") ? player.headshot : `${API_BASE}${player.headshot}`}
            alt={player.name}
            className="absolute bottom-0 right-4 h-[230px] w-[300px] object-contain object-bottom drop-shadow-[0_10px_18px_rgba(0,0,0,0.65)]"
          />

          <div className="absolute left-6 top-5 flex items-center gap-2.5">
            <span className="rounded bg-black/35 px-2 py-0.5 text-[11px] font-bold uppercase tracking-widest text-white/90">
              {player.team_abbr}
            </span>
            <span className="text-xs font-medium text-white/70">#{player.rank} overall</span>
            <span className="rounded-full bg-black/40 px-2 py-0.5 text-xs font-bold text-white">
              Tier {player.tier}
            </span>
          </div>

          <div className="absolute bottom-5 left-6 right-[320px]">
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-white/75">
              {player.name.split(" ")[0]}
              {profile?.nickname?.[0] && (
                <span className="ml-3 normal-case tracking-normal text-white/60">
                  “{profile.nickname[0]}”
                </span>
              )}
            </p>
            <h1 className="mt-0.5 truncate text-5xl font-black uppercase leading-none tracking-tight text-white [text-shadow:0_2px_6px_rgba(0,0,0,0.55)]">
              {player.name.split(" ").slice(1).join(" ") || player.name}
            </h1>
          </div>

          {/* racing stripe: one crisp accent line over the carbon */}
          <div
            className="absolute inset-x-0 bottom-0 h-[3px]"
            style={{
              background: `linear-gradient(90deg, ${colors.secondary} 0%, ${colors.secondary} 60%, transparent 96%)`,
              boxShadow: `0 0 12px ${colors.secondary}66`,
            }}
          />
        </div>

        {/* patch row — sewn under the banner like a jacket chest */}
        <div className="flex flex-wrap items-center justify-between gap-4 bg-[var(--surface-1)] px-6 py-4">
          {player.badges.length > 0 ? (
            <Patches badges={player.badges} />
          ) : (
            <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">
              No hardware yet — earn the patches
            </p>
          )}
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-3xl font-semibold tabular-nums">
                ${player.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
              <p
                className="text-sm font-medium"
                style={{ color: up ? "var(--delta-good)" : "var(--delta-bad)" }}
              >
                {up ? "▲" : "▼"} {Math.abs(player.change_30d_pct).toFixed(1)}%{" "}
                <span className="font-normal text-[var(--text-muted)]">30d</span>
              </p>
            </div>
            <button
              onClick={() => setTrade("buy")}
              className="rounded-lg bg-[var(--delta-good)] px-5 py-2.5 font-semibold text-white shadow-[0_4px_24px_-6px_rgba(12,163,12,0.55)] transition-all hover:opacity-90 active:scale-[0.98]"
            >
              Buy
            </button>
            <button
              onClick={() => setTrade("sell")}
              className="rounded-lg border border-[var(--border-hairline)] px-5 py-2.5 font-semibold transition-all hover:border-[var(--delta-bad)] hover:text-[var(--delta-bad)] active:scale-[0.98]"
            >
              Sell
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <section className="panel p-5">
            <SectionHeader label="Price history" />
            <div className="mt-3">
              {history ? (
                <PriceChart dates={history.dates} prices={history.prices} />
              ) : (
                <div className="h-56 animate-pulse rounded-lg bg-[var(--gridline)]" />
              )}
            </div>
          </section>

          <section className="panel p-5">
            <SectionHeader label="Why this price" />
            <div className="mt-4 max-w-md space-y-2.5">
              <BreakdownBar label="Perf" z={player.perf_z} />
              <BreakdownBar label="Pop" z={player.pop_z} />
              <BreakdownBar label="Team" z={player.team_z} />
            </div>
            <div className="mt-5 grid grid-cols-4 divide-x divide-[var(--border-hairline)] border-t border-[var(--border-hairline)] pt-4 sm:grid-cols-8">
              {[
                ["PPG", player.stats.pts.toFixed(1)],
                ["RPG", player.stats.reb.toFixed(1)],
                ["APG", player.stats.ast.toFixed(1)],
                ["SPG", player.stats.stl.toFixed(1)],
                ["BPG", player.stats.blk.toFixed(1)],
                ["MIN", player.stats.min.toFixed(1)],
                ["GP", String(player.stats.gp)],
                ["WIN%", `${Math.round(player.stats.team_win_pct * 100)}`],
              ].map(([label, value]) => (
                <div key={label} className="px-1 text-center">
                  <p className="text-lg font-semibold tabular-nums">{value}</p>
                  <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
                    {label}
                  </p>
                </div>
              ))}
            </div>
            {player.wiki_views && (
              <p className="mt-4 text-xs text-[var(--text-muted)]">
                Fame: {(player.wiki_views / 1e6).toFixed(1)}M Wikipedia views this season · GmSc{" "}
                {player.game_score.toFixed(1)}
              </p>
            )}
          </section>

          {profile?.ratings?.attributes && (
            <section className="panel p-5">
              <div className="flex items-center justify-between">
                <SectionHeader label="Scouting report" />
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-black tabular-nums">{profile.ratings.overall}</span>
                  <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
                    OVR
                  </span>
                </div>
              </div>
              <div className="mt-2 flex flex-col items-center gap-4 sm:flex-row">
                <Radar attributes={profile.ratings.attributes} />
                <div className="w-full space-y-3 text-sm">
                  {!!profile.ratings.strengths?.length && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
                        Strengths
                      </p>
                      <p className="mt-1 font-medium" style={{ color: "var(--delta-good)" }}>
                        {profile.ratings.strengths.join(" · ")}
                      </p>
                    </div>
                  )}
                  {!!profile.ratings.weaknesses?.length && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">
                        Weaknesses
                      </p>
                      <p className="mt-1 font-medium" style={{ color: "var(--delta-bad)" }}>
                        {profile.ratings.weaknesses.join(" · ")}
                      </p>
                    </div>
                  )}
                  <p className="text-xs leading-relaxed text-[var(--text-muted)]">
                    Attributes are league percentiles from this season&apos;s stats — the honest
                    version of a 2K rating.
                  </p>
                </div>
              </div>
            </section>
          )}

          {!!profile?.shot_zones?.length && (
            <section className="panel p-5">
              <SectionHeader label="Shot profile" />
              <div className="mt-4">
                <ShotZones zones={profile.shot_zones} />
              </div>
            </section>
          )}
        </div>

        <aside className="space-y-6">
          {profile?.bio && (
            <div className="panel p-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide">About</h2>
              {profile.nickname.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {profile.nickname.map((n) => (
                    <span
                      key={n}
                      className="rounded-full border border-[var(--border-hairline)] px-2 py-0.5 text-xs text-[var(--text-secondary)]"
                    >
                      “{n}”
                    </span>
                  ))}
                </div>
              )}
              <p className="mt-2.5 text-sm leading-relaxed text-[var(--text-secondary)]">
                {profile.bio.length > 420 ? `${profile.bio.slice(0, 420)}…` : profile.bio}
              </p>
              {profile.wiki_url && (
                <a
                  href={profile.wiki_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-xs text-[var(--series-pos)] hover:underline"
                >
                  Full bio on Wikipedia →
                </a>
              )}
            </div>
          )}
          <div className="lg:sticky lg:top-24">
            <FeedPanel playerId={player.player_id} title={`${player.name.split(" ").slice(-1)[0]} news`} />
          </div>
        </aside>
      </div>

      {trade && <TradeModal player={player} action={trade} onClose={() => setTrade(null)} />}
      </main>
    </div>
  );
}
