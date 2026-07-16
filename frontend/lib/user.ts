// Session identity: bearer token + username in localStorage, refresh via
// window event. The token is what the API trusts; username is for display.
const TOKEN_KEY = "nbastock:token";
const NAME_KEY = "nbastock:username";
export const REFRESH_EVENT = "nbastock:refresh";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(NAME_KEY);
}

export function setAuth(token: string | null, username: string | null) {
  if (token && username) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(NAME_KEY, username);
  } else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(NAME_KEY);
  }
  window.dispatchEvent(new Event(REFRESH_EVENT));
}

export function notifyRefresh() {
  window.dispatchEvent(new Event(REFRESH_EVENT));
}
