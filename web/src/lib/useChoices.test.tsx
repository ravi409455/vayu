import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FormSummary, FormVersion } from "../api/types";
import { useFieldChoices, useRefChoices } from "./useChoices";

const json = (x: unknown) => new Response(JSON.stringify(x), { status: 200, headers: { "Content-Type": "application/json" } });
const ver = (id: number, key: string, extra: Partial<FormVersion> = {}) =>
  ({
    id,
    pages: [{ sections: [{ fields: [{ key, label: key.toUpperCase(), type: "short_text" }] }] }],
    ...extra,
  }) as unknown as FormVersion;
const forms = [
  { id: 1, type: "booking", published_version: { id: 11 } },
  { id: 2, type: "start", published_version: { id: 21 } },
  { id: 3, type: "custom", published_version: { id: 31, use_start: false }, draft_version: { id: 32, use_start: false } },
  { id: 4, type: "custom", published_version: { id: 41 } },
];
const versions: Record<string, FormVersion> = {
  11: ver(11, "city"),
  21: ver(21, "selfie"),
  32: ver(32, "door", { key_checks: [{ key: "k", label: "Rust", in_report: true }] } as never),
};
const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

afterEach(() => vi.restoreAllMocks());

describe("one hook builds the fields of all forms (F-030)", () => {
  const serve = () =>
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u) => {
      const url = String(u).split("?")[0]!;
      if (url.endsWith("/forms")) return json(forms);
      return json(versions[url.split("/").pop()!]);
    });
  it("a PDF template sees the booking and its own draft, plus its Key Checks; no start when the form skips it", async () => {
    serve();
    const { result } = renderHook(() => useRefChoices(3), { wrapper: wrap });
    await waitFor(() => expect(result.current.length).toBeGreaterThan(0));
    expect(result.current.map((c) => c.value)).toEqual(["booking.city", "inspection.door", "check.k"]);
  });
  it("the builder sees the version being edited plus the other forms' published ones", async () => {
    serve();
    const own = forms[3] as unknown as FormSummary;
    const { result } = renderHook(() => useFieldChoices(own, ver(41, "tyre")), { wrapper: wrap });
    await waitFor(() => expect(result.current.length).toBe(3));
    expect(result.current.map((c) => c.label)).toEqual(["inspection: TYRE", "booking: CITY", "start: SELFIE"]);
  });
});
