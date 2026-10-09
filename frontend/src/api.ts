import type { Dict } from "./types";

export const api = async (path: string, options?: RequestInit) => {
  const r = await fetch("/api" + path, options);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(
      typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail),
    );
  }
  return r.json();
};
export const post = (path: string, body: Dict = {}) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
