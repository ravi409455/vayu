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
    this.name = "ApiError"; // kept by the minifier, so monitoring can tell it apart
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
  opts: { method?: string; body?: unknown; query?: Record<string, string | number | undefined>; signal?: AbortSignal } = {},
): Promise<T> {
  const method = opts.method ?? (opts.body === undefined ? "GET" : "POST");
  const q = opts.query
    ? "?" +
      new URLSearchParams(
        Object.entries(opts.query)
          .filter(([, v]) => v !== undefined && v !== "")
          .map(([k, v]) => [k, String(v)]),
      ).toString()
    : "";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();
  const res = await fetch(`/api/v1/${path.replace(/^\//, "")}${q}`, {
    method,
    headers,
    credentials: "same-origin",
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
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
  const fields = e.body && typeof e.body === "object" ? Object.entries(e.body).filter(([k]) => !["code", "detail"].includes(k)) : [];
  const first = fields.find(([, v]) => typeof v === "string" || (Array.isArray(v) && typeof v[0] === "string"));
  if (e.message.startsWith("Request failed") && first) {
    const v = first[1];
    return `${first[0]}: ${Array.isArray(v) ? v[0] : v}`;
  }
  // a field error: the server's detail is the first field's message; say which field it is
  const named =
    e.body?.fields && typeof e.body.fields === "object" ? Object.entries(e.body.fields as Record<string, unknown>)[0] : undefined;
  if (named && named[0] !== "non_field_errors" && Array.isArray(named[1]) && named[1][0] === e.message)
    return `${named[0].replace(/_/g, " ")}: ${e.message}`;
  return e.message;
}

/** An INVALID_ANSWERS refusal, per field: the server's sentence (the Admin's own check message
 *  included) where it sent one, never a bare code. Null for any other error. */
export function answerErrors(e: unknown): Record<string, string> | null {
  if (!(e instanceof ApiError) || !e.body.errors || typeof e.body.errors !== "object") return null;
  const said = (e.body.messages && typeof e.body.messages === "object" ? e.body.messages : {}) as Record<string, unknown>;
  return Object.fromEntries(
    Object.entries(e.body.errors as Record<string, unknown>).map(([k, v]) => [
      k,
      typeof said[k] === "string" ? (said[k] as string) : String(v),
    ]),
  );
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

/** Upload one file as multipart form data (the builder's pictures). */
export async function uploadFile<T>(
  path: string,
  file: File,
  method: "POST" | "PUT" = "POST",
  fields: Record<string, string> = {},
): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  for (const [k, v] of Object.entries(fields)) body.append(k, v);
  const res = await fetch(`/api/v1/${path.replace(/^\//, "")}`, {
    method,
    body,
    credentials: "same-origin",
    headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" },
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const err = new ApiError(res.status, data);
    if (res.status === 401) handlers.onUnauthorized?.();
    throw err;
  }
  return data as T;
}
