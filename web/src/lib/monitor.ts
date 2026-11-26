// Web errors go to Sentry (R-36) only when VITE_SENTRY_DSN is set at build time; otherwise the SDK
// is never even loaded. Nothing private leaves the browser: no request bodies, cookies, query
// strings (they can hold a customer's phone or name), typed text or console output.
import type { Breadcrumb, ErrorEvent } from "@sentry/react";

type Sdk = typeof import("@sentry/react");
let sdk: Sdk | null = null;

let person: number | null = null;

/** No query string, and no report or ZIP token: on the customer pages the secret is in the path
 *  (/report/verify/<token>[/<link>], /zip/<token>, /api/v1/verify/<token>). */
export const stripQuery = (url: string) => url.replace(/[?#].*$/, "").replace(/\/(verify|zip)\/[^/]+(\/[^/]+)?/, "/$1/[token]");

/** What leaves for Sentry: the error and where it happened, never what people typed or the server sent. */
export function scrub(e: ErrorEvent): ErrorEvent {
  if (e.request) e.request = { url: e.request.url ? stripQuery(e.request.url) : undefined };
  if (e.user) e.user = e.user.id !== undefined ? { id: e.user.id } : undefined;
  if (e.transaction) e.transaction = stripQuery(e.transaction);
  // an unhandled API error's message is the server's sentence, which can name a customer
  for (const x of e.exception?.values ?? []) if (x.type === "ApiError") x.value = "ApiError";
  delete e.extra;
  return e;
}
export function scrubCrumb(b: Breadcrumb): Breadcrumb | null {
  if (b.category === "console" || b.category === "ui.input") return null;
  // a click's description is the element's selector, which can hold its label ("Call 98765…"): keep only that it happened
  if (b.category?.startsWith("ui.")) return { ...b, message: undefined, data: undefined };
  const d = b.data as Record<string, unknown> | undefined;
  if (d) for (const k of ["url", "from", "to"]) if (typeof d[k] === "string") d[k] = stripQuery(d[k] as string);
  return b;
}

/** One web build serves staging and production, so the label comes from the address it is opened on. */
export function sentryEnvironment(host = location.hostname): string {
  const set = import.meta.env.VITE_SENTRY_ENV as string | undefined;
  if (set) return set;
  if (!import.meta.env.PROD) return import.meta.env.MODE;
  return host.includes("staging") ? "staging" : "production";
}

export async function startMonitoring(dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined): Promise<void> {
  if (!dsn) return;
  const S = await import("@sentry/react");
  S.init({
    dsn,
    environment: sentryEnvironment(),
    release: import.meta.env.VITE_RELEASE as string | undefined,
    // collect nothing about people or requests; scrub() and scrubCrumb() check again before sending
    dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false },
    beforeSend: scrub,
    beforeBreadcrumb: scrubCrumb,
  });
  sdk = S;
  setPerson(person); // the person may have signed in before the SDK finished loading
}

/** Report something that went wrong (a page crash, an upload that will not go). No-op without a DSN. */
export function report(error: unknown, tags?: Record<string, string>): void {
  sdk?.captureException(error, { tags });
}
/** Who is signed in, by id only, so errors can be grouped per person without their name. */
export function setPerson(id: number | null): void {
  person = id;
  sdk?.setUser(id === null ? null : { id: String(id) });
}
