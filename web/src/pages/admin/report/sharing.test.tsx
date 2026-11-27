import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { keys } from "../../../api/keys";
import { useShared, useSharedContent } from "./sharing";

afterEach(() => vi.restoreAllMocks());

// J1 flake: with no theme linked yet, the content query took the list's own key, so the two shared
// one cache entry and a list refresh could run the content fetch (no item) and keep the old list
it("a theme's content never shares the shared list's cache entry", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  const qc = new QueryClient();
  const Page = () => {
    useShared();
    useSharedContent(undefined, undefined);
    return null;
  };
  render(
    <QueryClientProvider client={qc}>
      <Page />
    </QueryClientProvider>,
  );
  const list = qc.getQueryCache().find({ queryKey: keys.pdfShared(), exact: true })!;
  await waitFor(() => expect(list.state.status).toBe("success"));
  expect(list.getObserversCount()).toBe(1);
});
