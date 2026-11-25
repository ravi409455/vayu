import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../../auth";
import { FormBuilder, PublishDialog } from "./FormBuilder";

afterEach(() => vi.restoreAllMocks());

const noop = () => {};

describe("publish dialog", () => {
  it("lists blocking problems and hides the publish button", () => {
    render(
      <PublishDialog
        state={{ issues: [{ path: "fields.door", code: "X", message: "needs options" }], warnings: [], done: false }}
        onClose={noop}
        onPublish={noop}
      />,
    );
    expect(screen.getByText("Fix these first")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("needs options");
    expect(screen.queryByRole("button", { name: "Publish now" })).toBeNull();
  });
  it("asks for a last confirmation when clean, and shows PDF warnings afterwards", async () => {
    const onPublish = vi.fn();
    const u = userEvent.setup();
    const { rerender } = render(<PublishDialog state={{ issues: [], warnings: [], done: false }} onClose={noop} onPublish={onPublish} />);
    await u.click(screen.getByRole("button", { name: "Publish now" }));
    expect(onPublish).toHaveBeenCalled();
    rerender(
      <PublishDialog
        state={{
          issues: [],
          warnings: [{ path: "", code: "FIELD_NOT_IN_PDF", message: "Field 'odometer' is not shown in the PDF template." }],
          done: true,
        }}
        onClose={noop}
        onPublish={noop}
      />,
    );
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText(/odometer/)).toBeInTheDocument();
  });
});

describe("the form builder's publish button", () => {
  it("is not clickable until the draft's version has loaded (a click before that did nothing)", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("auth/me"))
        return ok({
          id: 1,
          username: "a",
          name: "A",
          role: "admin",
          permissions: { "forms.edit": "all", "forms.publish": "all", "forms.view": "all" },
        });
      if (url.includes("form-versions/7")) {
        await gate;
        return ok({ id: 7, form: 1, number: 2, status: "draft", published_at: null, row_version: 0, pages: [], checks: [] });
      }
      if (url.endsWith("forms/1"))
        return ok({
          id: 1,
          key: "pdi",
          type: "custom",
          name: "PDI",
          is_active: true,
          inspection_type: "pdi",
          draft_version: { id: 7, number: 2 },
          published_version: { id: 6, number: 1 },
        });
      return ok([]);
    });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/forms/1"]}>
          <AuthProvider>
            <Routes>
              <Route path="/forms/:id" element={<FormBuilder />} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const publish = await screen.findByRole("button", { name: /Check & publish/ });
    expect(publish).toBeDisabled();
    release();
    await waitFor(() => expect(publish).toBeEnabled());
  });
});
