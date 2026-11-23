import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import type { FormField, FormPage } from "./api/types";
import { Forms } from "./pages/admin/Forms";
import { FormRenderer } from "./ui/FormRenderer";

afterEach(() => vi.restoreAllMocks());

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const form = (id: number, key: string, type: string, name: string, over: Record<string, unknown> = {}) => ({
  id, key, type, name, is_active: true, inspection_type: type === "custom" ? key : "", submission_roles: ["expert", "ops"],
  draft_version: null, published_version: { id: id * 10, number: 1, use_start: true, use_end: true }, ...over,
});
const FORMS = [form(1, "booking", "booking", "Booking"), form(2, "start", "start", "Start"), form(3, "end", "end", "End"),
  form(4, "pdi", "custom", "PDI (new car)"), form(5, "ev", "custom", "EV", { published_version: null, draft_version: { id: 50, number: 1 } }),
  form(6, "old", "custom", "Old form", { is_active: false })];

function serve(routes: Record<string, (init?: RequestInit) => unknown>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    for (const [prefix, fn] of Object.entries(routes)) if (url.includes(prefix)) return json(fn(init));
    return json({ detail: "not found" }, 404);
  });
  return calls;
}
const shell = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><AuthProvider>{ui}</AuthProvider></MemoryRouter>
  </QueryClientProvider>);

describe("the Forms page", () => {
  const me = { id: 1, username: "a", name: "A", role: "admin", permissions: { "forms.edit": "all", "forms.view": "all" } };
  it("shows the three system forms apart from the custom forms, and marks a switched-off one", async () => {
    serve({ "auth/me": () => me, "/forms": () => ({ count: 6, next: null, previous: null, results: FORMS }) });
    shell(<Forms />);
    const system = within(await screen.findByRole("table", { name: "System forms" }));
    await waitFor(() => expect(system.getAllByRole("row")).toHaveLength(4));
    expect(system.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[1]!.textContent)).toEqual(["Booking form", "Start form", "End form"]);
    const custom = within(screen.getByRole("table", { name: "Custom forms" }));
    expect(custom.getByText("PDI (new car)")).toBeInTheDocument();
    expect(custom.getByText("Not published")).toBeInTheDocument();           // EV has only a draft
    expect(custom.getByText("Switched off")).toBeInTheDocument();
    expect(screen.queryByText(/delete/i)).toBeNull();                       // nothing can be removed here
  });
  it("creates a custom form from just a name and a key", async () => {
    const calls = serve({ "auth/me": () => me, "forms": (init) => (init?.method === "POST" ? form(9, "ppi", "custom", "PPI") : { count: 0, next: null, previous: null, results: [] }) });
    const u = userEvent.setup();
    shell(<Forms />);
    await u.click(await screen.findByRole("button", { name: "New custom form" }));
    expect(screen.queryByLabelText("Kind")).toBeNull();                       // no type picker any more
    await u.type(screen.getByLabelText("Name"), "PPI");
    await u.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST" && c.url.endsWith("/forms"))).toBe(true));
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(post.init!.body))).toEqual({ name: "PPI", key: "ppi" });
  });
});

describe("the booking form's inspection type", () => {
  const f: FormField = {
    id: 1, section: 1, key: "inspection_type", label: "Inspection type", helper_text: "", type: "form_choice", config: {}, required: true, required_if: null, show_if: null,
    visible: true, order: 0, is_system: true, access: {}, locked: false, library: null,
  };
  const page: FormPage = { id: 1, title: "P", order: 0, visible: true, gate: false, show_if: null, access: {}, sections: [{ id: 1, page: 1, title: "S", order: 0, visible: true, show_if: null, access: {}, fields: [f], locked: false, library: null }] };
  const types = [{ key: "pdi", label: "PDI (new car)", available: true }, { key: "ev", label: "EV", available: false }, { key: "old", label: "Old form", available: false }];

  it("is a pick from the custom forms by name, offering only the ones that are live", async () => {
    serve({ "inspection-types": () => types });
    shell(<FormRenderer kind="booking" tree={{ pages: [page], checks: [] }} values={{}} onChange={() => {}} />);
    const select = await screen.findByLabelText("Inspection type");
    await waitFor(() => expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "PDI (new car)"]));
  });
  it("still shows the form a booking already has, even if it was switched off since", async () => {
    serve({ "inspection-types": () => types });
    shell(<FormRenderer kind="booking" tree={{ pages: [page], checks: [] }} values={{ inspection_type: "old" }} onChange={() => {}} />);
    await waitFor(() => expect(within(screen.getByLabelText("Inspection type")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "PDI (new car)", "Old form"]));
    expect(screen.getByLabelText("Inspection type")).toHaveValue("old");
  });
  it("tells the parent which form key was chosen", async () => {
    serve({ "inspection-types": () => types });
    const onChange = vi.fn();
    const u = userEvent.setup();
    shell(<FormRenderer kind="booking" tree={{ pages: [page], checks: [] }} values={{}} onChange={onChange} />);
    await waitFor(() => expect(within(screen.getByLabelText("Inspection type")).getAllByRole("option")).toHaveLength(2));
    await u.selectOptions(screen.getByLabelText("Inspection type"), "pdi");
    expect(onChange).toHaveBeenCalledWith("inspection_type", "pdi");
  });
});

describe("system fields in the field editor", () => {
  const mode = { id: 9, section: 1, key: "payment_mode", label: "Payment mode", helper_text: "", type: "single_choice", required: false, required_if: null, show_if: null,
    config: { options: [{ key: "cash", label: "Cash" }, { key: "upi", label: "UPI" }] }, visible: true, order: 0, is_system: true, access: {}, locked: false, library: null } as FormField;
  it("lists and lets the Admin change the choices of a system choice field, like any other choice field", async () => {
    const { FieldEditor } = await import("./pages/admin/FieldEditor");
    const onSave = vi.fn();
    const u = userEvent.setup();
    render(<FieldEditor field={mode} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={() => {}} readOnly={false} />);
    expect(screen.getAllByLabelText("Choice label").map((i) => (i as HTMLInputElement).value)).toEqual(["Cash", "UPI"]);
    await u.click(screen.getByRole("button", { name: "+ Add choice" }));
    const keys = screen.getAllByLabelText("Choice key");
    await u.type(keys[2]!, "wallet");
    await u.type(screen.getAllByLabelText("Choice label")[2]!, "Wallet");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave.mock.calls[0]![0].config.options).toEqual([{ key: "cash", label: "Cash" }, { key: "upi", label: "UPI" }, { key: "wallet", label: "Wallet" }]);
  });
  it("still keeps a library-linked field's choices read-only", async () => {
    const { FieldEditor } = await import("./pages/admin/FieldEditor");
    render(<FieldEditor field={{ ...mode, is_system: false, locked: true }} choices={[]} lists={[]} categories={[]} onSave={() => {}} onDelete={() => {}} readOnly />);
    expect(screen.queryByLabelText("Choice key")).toBeNull();
  });
});
