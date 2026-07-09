// Session-lite identity: username in localStorage, refresh via window event.
const KEY = "nbastock:username";
export const REFRESH_EVENT = "nbastock:refresh";

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(KEY);
}

export function setUsername(username: string | null) {
  if (username) localStorage.setItem(KEY, username);
  else localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(REFRESH_EVENT));
}

export function notifyRefresh() {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}
