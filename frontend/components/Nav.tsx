"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { enterMarket, fetchPortfolio, logout } from "@/lib/api";
import { getUsername, REFRESH_EVENT, setAuth } from "@/lib/user";

const LINKS = [
  { href: "/", label: "Market" },
  { href: "/portfolio", label: "Portfolio" },
  { href: "/leaderboard", label: "Leaderboard" },
];

export default function Nav() {
  const pathname = usePathname();
  const [user, setUser] = useState<string | null>(null);
  const [cash, setCash] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    const u = getUsername();
    setUser(u);
    if (u) {
      fetchPortfolio()
        .then((p) => setCash(p.cash))
        .catch(() => {
          setCash(null);
          setAuth(null, null); // token expired or revoked
        });
    } else {
      setCash(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(REFRESH_EVENT, refresh);
    return () => window.removeEventListener(REFRESH_EVENT, refresh);
  }, [refresh]);

  async function enter() {
    if (!name.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      const r = await enterMarket(name.trim(), password);
      setAuth(r.token, r.username);
      setName("");
      setPassword("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't sign in");
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      await logout();
    } catch {
      // token already dead — still clear locally
    }
    setAuth(null, null);
  }

  return (
    <nav className="sticky top-0 z-40 border-b border-[var(--border-hairline)] bg-[rgba(13,13,13,0.85)] backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-sm font-bold uppercase tracking-[0.2em] text-[var(--text-primary)]">
          NBAStock
        </Link>
        <div className="flex gap-1">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                pathname === l.href
                  ? "bg-[var(--surface-1)] font-medium text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-3">
          {user ? (
            <>
              {cash !== null && (
                <span className="rounded-full border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-1 text-sm tabular-nums text-[var(--text-primary)]">
                  ${cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </span>
              )}
              <span className="text-sm text-[var(--text-secondary)]">@{user}</span>
              <button
                onClick={signOut}
                className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                Sign out
              </button>
            </>
          ) : (
            <div className="flex items-center gap-2">
              {error && <span className="max-w-52 truncate text-xs text-[var(--delta-bad)]" title={error}>{error}</span>}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Username"
                autoComplete="username"
                className="w-32 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-1.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[rgba(255,255,255,0.3)]"
              />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && enter()}
                placeholder="Password"
                autoComplete="current-password"
                className="w-32 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-1.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[rgba(255,255,255,0.3)]"
              />
              <button
                onClick={enter}
                disabled={busy}
                className="whitespace-nowrap rounded-lg bg-[var(--series-pos)] px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
                title="New username? You're registered with $10k. Existing? You're signed in."
              >
                {busy ? "…" : "Enter · $10k"}
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
