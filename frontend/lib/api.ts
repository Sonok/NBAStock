export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Player {
  player_id: number;
  name: string;
  team_id: number;
  team_abbr: string;
  price: number;
  composite: number;
  perf_z: number;
  pop_z: number;
  team_z: number;
  momentum_z: number;
  game_score: number;
  tier: "S" | "A" | "B" | "C" | "D";
  rank: number;
  headshot: string;
  spark: number[];
  change_30d_pct: number;
  wiki_views: number | null;
  stats: {
    gp: number;
    min: number;
    pts: number;
    reb: number;
    ast: number;
    stl: number;
    blk: number;
    team_win_pct: number;
  };
}

export interface PlayersResponse {
  season: string;
  count: number;
  players: Player[];
}

export interface Holding {
  player_id: number;
  shares: number;
  avg_cost: number;
  price: number;
  market_value: number;
  unrealized_pl: number;
  name: string;
  team_abbr: string;
  tier: Player["tier"];
  headshot: string;
}

export interface Portfolio {
  username: string;
  cash: number;
  market_value: number;
  equity: number;
  total_return_pct: number;
  holdings: Holding[];
}

export interface MarketEvent {
  id: number;
  ts: string;
  player_id: number;
  name: string;
  type: "price_move" | "news" | "signal";
  message: string;
  delta_pct: number | null;
  url: string | null;
}

export async function fetchFeed(): Promise<{ events: MarketEvent[] }> {
  const res = await fetch(`${API_BASE}/api/feed`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export interface LeaderboardRow {
  rank: number;
  username: string;
  equity: number;
  total_return_pct: number;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail ?? `API error ${res.status}`);
  return data;
}

export function login(username: string): Promise<{ username: string; cash: number }> {
  return post("/api/users", { username });
}

export function executeTrade(params: {
  username: string;
  player_id: number;
  shares: number;
  action: "buy" | "sell";
}): Promise<{ cash: number; shares: number; avg_cost: number; executed_price: number }> {
  return post("/api/trade", params);
}

export async function fetchPortfolio(username: string): Promise<Portfolio> {
  const res = await fetch(`${API_BASE}/api/users/${encodeURIComponent(username)}/portfolio`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchLeaderboard(): Promise<{ leaderboard: LeaderboardRow[] }> {
  const res = await fetch(`${API_BASE}/api/leaderboard`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}

export async function fetchPlayers(params: {
  limit?: number;
  search?: string;
  team?: string;
}): Promise<PlayersResponse> {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.search) qs.set("search", params.search);
  if (params.team) qs.set("team", params.team);
  const res = await fetch(`${API_BASE}/api/players?${qs}`);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
