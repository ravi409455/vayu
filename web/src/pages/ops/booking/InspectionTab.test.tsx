import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../../auth";
import { ToastProvider } from "../../../ui/kit";
import { InspectionTab } from "./InspectionTab";

afterEach(() => vi.restoreAllMocks());
const json = (x: unknown) => new Response(JSON.stringify(x), { status: 200, headers: { "Content-Type": "application/json" } });

function mount() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
    String(url).includes("auth/me") ? json({ id: 1, username: "o", role: "ops", permissions: { "submissions.view": "all" } }) : json([]),
  );
  const page = { id: "p1", title: "Body", sections: [{ id: "s1", title: "Body", fields: [] }] };
  const trees = {
    inspection: {
      pages: [page],
      key_checks: [
        { key: "engine", label: "Engine work done" },
        { key: "price", label: "Price estimate" },
        { key: "rust", label: "Rusting in body" },
      ],
    },
    start: null,
    end: null,
  };
  const insp = {
    id: "i1",
    row_version: 1,
    status: "submitted",
    answers: { inspection: {}, start: {}, end: {} },
    scores: { key_checks: { engine: { value: "No" }, rust: { value: "Not Found" }, price: { value: "" } } },
  };
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AuthProvider>
          <ToastProvider>
            <InspectionTab
              booking={{ id: "b1", stage: "completed" } as never}
              insp={insp as never}
              trees={trees as never}
              activity={[]}
              onSaved={() => {}}
            />
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Key Checks on the Inspection tab", () => {
  it("the summary shows only a count; the full list opens in a pop-up that closes", async () => {
    mount();
    const summary = screen.getByRole("region", { name: "Inspection summary" });
    expect(within(summary).getByText(/of 3 filled/)).toBeInTheDocument();
    expect(within(summary).queryByText(/Engine work done/)).toBeNull();

    await userEvent.click(within(summary).getByRole("button", { name: "See all 3" }));
    const dialog = await screen.findByRole("dialog", { name: "Key Checks" });
    const filled = within(dialog).getByRole("region", { name: "Filled" });
    expect(within(filled).getByText("Engine work done")).toBeInTheDocument();
    expect(within(filled).getByText("Not Found")).toBeInTheDocument();
    const empty = within(dialog).getByRole("region", { name: "Not filled" });
    expect(within(empty).getByText("Price estimate")).toBeInTheDocument();
    expect(within(empty).getByText("—")).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Key Checks" })).toBeNull();
  });
});
