// One place that talks to the API: session cookie + CSRF header, JSON in and out, and a typed
// error that every screen handles the same way (401 sign-in, 403, 409 changed-by-someone, 426).
export class ApiError extends Error {
  status: number;
  code: string;
  body: Record<string, unknown>;
  constructor(status: number, body: Record<string, unknown>) {
    const detail = body.detail;
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.status = status;
    this.code = typeof body.code === "string" ? body.code : `HTTP_${status}`;
    this.body = body;
  }
}

type Handlers = { onUnauthorized?: () => void; onUpgrade?: () => void };
const handlers: Handlers = {};
export function setApiHandlers(h: Handlers): void {
  Object.assign(handlers, h);
}

export function csrfToken(): string {
  const m = /(?:^|; )csrftoken=([^;]+)/.exec(document.cookie);
  return m?.[1] ? decodeURIComponent(m[1]) : "";
}

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; query?: Record<string, string | number | undefined> } = {},
): Promise<T> {
  const method = opts.method ?? (opts.body === undefined ? "GET" : "POST");
  const q = opts.query
    ? "?" + new URLSearchParams(Object.entries(opts.query).filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)])).toString()
    : "";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();
  const res = await fetch(`/api/v1/${path.replace(/^\//, "")}${q}`, {
    method,
    headers,
    credentials: "same-origin",
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("Content-Type") ?? "";
  const data = type.includes("json") ? await res.json() : {};
  if (!res.ok) {
    const err = new ApiError(res.status, (data ?? {}) as Record<string, unknown>);
    if (res.status === 401 && err.code !== "INVALID_CREDENTIALS") handlers.onUnauthorized?.();
    if (res.status === 426) handlers.onUpgrade?.();
    throw err;
  }
  return data as T;
}

/** What to tell the person, in plain words. Screens never show raw codes. */
export function explain(e: unknown): string {
  if (!(e instanceof ApiError)) return "Something went wrong. Check your connection and try again.";
  if (e.status === 403) return "You are not allowed to do that.";
  if (e.status === 426) return "This app is out of date. Reload the page.";
  if (e.status === 429) return "Too many tries. Wait a minute and try again.";
  if (e.status >= 500) return "The server had a problem. Try again in a moment.";
  const fields = e.body && typeof e.body === "object"
    ? Object.entries(e.body).filter(([k]) => !["code", "detail"].includes(k)) : [];
  const first = fields.find(([, v]) => typeof v === "string" || (Array.isArray(v) && typeof v[0] === "string"));
  if (e.message.startsWith("Request failed") && first) {
    const v = first[1];
    return `${first[0]}: ${Array.isArray(v) ? v[0] : v}`;
  }
  return e.message;
}

/** A 409 "someone else saved first" carries who, when and which fields. */
export function staleInfo(e: unknown): { by: string; at: string; keys: string[]; rowVersion: number } | null {
  if (!(e instanceof ApiError) || e.status !== 409 || !e.code.startsWith("STALE_")) return null;
  const b = e.body;
  return {
    by: String(b.changed_by ?? "someone"),
    at: String(b.changed_at ?? ""),
    keys: Array.isArray(b.changed_keys) ? (b.changed_keys as string[]) : [],
    rowVersion: Number(b.row_version ?? 0),
  };
}
