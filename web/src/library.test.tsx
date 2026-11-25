import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import type { FormSummary } from "./api/types";
import { Library } from "./pages/admin/Library";
import { LibraryEditor } from "./pages/admin/LibraryEditor";
import { DuplicateDialog, ImportDialog } from "./pages/admin/builder/ImportForm";
import { describeChange, PushReview } from "./pages/admin/library/PushReview";

afterEach(() => vi.restoreAllMocks());

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const ME = { id: 1, username: "a", name: "A", role: "admin", permissions: { "library.edit": "all", "library.view": "all", "forms.edit": "all", "forms.view": "all", "forms.promote": "all" } };
type Handler = (init?: RequestInit, url?: string) => { status?: number; body: unknown } | unknown;
function serve(routes: Record<string, Handler>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    const hit = Object.entries(routes).filter(([p]) => url.includes(p)).sort((a, b) => b[0].length - a[0].length)[0];
    if (!hit) return json({ detail: "not found" }, 404);
    const out = hit[1](init, url) as { status?: number; body?: unknown } | unknown;
    return out && typeof out === "object" && "body" in (out as object) ? json((out as { body: unknown }).body, (out as { status?: number }).status ?? 200) : json(out);
  });
  return calls;
}
const shell = (ui: React.ReactNode, path = "/") => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}><AuthProvider>{ui}</AuthProvider></MemoryRouter>
  </QueryClientProvider>);

const FORMS: FormSummary[] = [
  { id: 1, key: "pdi", type: "custom", name: "PDI", is_active: true, inspection_type: "pdi", draft_version: null, published_version: { id: 10, number: 1 } },
  { id: 2, key: "start", type: "start", name: "Start", is_active: true, inspection_type: "", draft_version: null, published_version: { id: 20, number: 1 } },
];

describe("the library list", () => {
  it("shows how many forms use each item, filters, and offers New item to Admins", async () => {
    const calls = serve({ "auth/me": () => ME, "library": () => ({ count: 1, next: null, previous: null, results: [{ id: 7, kind: "section", key: "tyres", name: "Tyres", revision: 3, archived: false, used_in: 2 }] }) });
    const u = userEvent.setup();
    shell(<Library />);
    expect(await screen.findByRole("link", { name: "Tyres" })).toHaveAttribute("href", "/library/7");
    expect(screen.getByText("2 forms")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New item" })).toBeInTheDocument();
    await u.click(within(screen.getByRole("group", { name: "Kind" })).getByRole("button", { name: "Fields" }));
    await u.click(screen.getByLabelText("Show archived"));
    await waitFor(() => expect(calls.some((c) => c.url.includes("kind=field") && c.url.includes("include_archived=1"))).toBe(true));
  });
});

describe("the update-everywhere review", () => {
  const form = (over: object = {}) => ({ form: "pdi", type: "custom", state: "draft", changes: [{ target: "door", setting: "required", from: false, to: true }], problems: [], ...over });
  const open = (report: unknown, extra: Record<string, Handler> = {}) => {
    const calls = serve({ "push-preview": () => report, "/push": (init) => ({ forms: [{ form: "pdi" }], skipped: [], blocked: false, ...JSON.parse(String(init?.body)) && {} }), ...extra });
    const onDone = vi.fn();
    shell(<PushReview itemId={7} itemName="Tyres" revision={3} onClose={() => {}} onDone={onDone} />);
    return { calls, onDone };
  };

  it("lists each form with what changes and keeps publishing off until confirmed", async () => {
    const u = userEvent.setup();
    const { calls } = open({ forms: [form(), form({ form: "ev", state: "published_only", changes: [] })], skipped: [{ form: "old", reason: "inactive" }], blocked: false });
    expect(await screen.findByText("door: required false → true")).toBeInTheDocument();
    expect(screen.getByText(/its open draft is updated/)).toBeInTheDocument();
    expect(screen.getByText(/a new draft is made/)).toBeInTheDocument();
    expect(screen.getByText(/Skipped \(switched off\): old/)).toBeInTheDocument();
    const publish = screen.getByLabelText("Publish automatically after updating");
    expect(publish).not.toBeChecked();                                       // off by default
    expect(screen.getByRole("button", { name: "Update 2 forms" })).toBeEnabled();
    await u.click(publish);
    expect(screen.getByText(/puts 2 forms live/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update and publish 2 forms" })).toBeDisabled();   // needs the confirmation
    await u.click(screen.getByLabelText(/I understand this puts 2 forms live/));
    await u.click(screen.getByRole("button", { name: "Update and publish 2 forms" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/push"))).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("/push"))!.init!.body))).toEqual({ revision: 3, publish: true, confirm: true });
  });
  it("blocks the button while any problem exists and shows it", async () => {
    open({ forms: [form({ problems: [{ form: "pdi", path: "definition", code: "UNKNOWN_FIELD", message: "'inspection.depth_fr' is not a field of the inspection form." }] })], skipped: [], blocked: true });
    expect(await screen.findByText(/depth_fr/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update 1 form" })).toBeDisabled();
    expect(screen.getByText(/Nothing was changed/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Publish automatically after updating")).toBeNull();
  });
  it("says so when there is nothing to update, and reports the result after a push", async () => {
    const { onDone } = open({ forms: [], skipped: [], blocked: false });
    expect(await screen.findByText(/already up to date/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nothing to update" })).toBeDisabled();
    expect(onDone).not.toHaveBeenCalled();
  });
  it("words every kind of change plainly", () => {
    expect(describeChange({ target: "a", setting: "added", from: false, to: true })).toBe("a: added");
    expect(describeChange({ target: "a", setting: "removed", from: true, to: false })).toBe("a: removed");
    expect(describeChange({ target: "a", setting: "show_if", from: null, to: { "!!": [1] } })).toBe('a: show if nothing → {"!!":[1]}');
  });
});

describe("the library item editor", () => {
  const ITEM = { id: 7, kind: "section", key: "tyres", name: "Tyres", revision: 2, archived: false,
    definition: { title: "Tyres", visible: true, fields: [{ key: "fl", label: "Front left", type: "number", config: {} }, { key: "fr", label: "Front right", type: "number", config: {} }] },
    usages: [{ form: "pdi", version: 1, status: "draft" }] };
  const HISTORY = [{ revision: 2, name: "Tyres", definition: ITEM.definition, changed_keys: ["fl"], by: "asha", at: "2026-11-23T10:00:00Z" },
    { revision: 1, name: "Tyres", definition: { ...ITEM.definition, title: "Old tyres" }, changed_keys: [], by: "asha", at: "2026-11-20T10:00:00Z" }];
  const open = (extra: Record<string, Handler> = {}) => {
    const calls = serve({ "auth/me": () => ME, "library/7/history": () => HISTORY, "library/7": (init) => (init?.method === "PATCH" ? { ...ITEM, revision: 3 } : ITEM), "master-lists": () => ({ count: 0, next: null, previous: null, results: [] }), ...extra });
    shell(<Routes><Route path="/library/:id" element={<LibraryEditor />} /></Routes>, "/library/7");
    return calls;
  };

  it("starts with Save off, saves a changed definition with the revision it started from, and says so", async () => {
    const calls = open();
    const u = userEvent.setup();
    const title = await screen.findByLabelText("Section title");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();            // nothing changed
    await u.clear(title);
    await u.type(title, "Tyre set");
    expect(screen.getByText(/^Unsaved changes/)).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body));
    expect(body.revision).toBe(2);
    expect(body.definition.title).toBe("Tyre set");
  });
  it("reorders and removes fields, and previews the section live", async () => {
    open();
    const u = userEvent.setup();
    await screen.findByLabelText("Section title");
    await u.click(screen.getByRole("button", { name: "Move Front right up" }));
    const labels = screen.getAllByRole("listitem").map((li) => li.textContent ?? "").filter((t) => /Front/.test(t));
    expect(labels[0]).toContain("Front right");
    await u.click(screen.getByRole("button", { name: "Remove Front left" }));
    expect(screen.queryByRole("button", { name: "Move Front left down" })).toBeNull();
    expect(within(screen.getByLabelText("Preview")).queryByText("Front left")).toBeNull();
  });
  it("tells the Admin when someone else saved first", async () => {
    open({ "library/7": (init) => (init?.method === "PATCH" ? { status: 409, body: { code: "STALE_LIBRARY_ITEM", detail: "stale", revision: 3 } } : ITEM) });
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Section title"), "!");
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Someone else saved this item")).toBeInTheDocument();
  });
  it("shows the server's reason when a rule reaches outside the item", async () => {
    open({ "library/7": (init) => (init?.method === "PATCH" ? { status: 400, body: { code: "RULE_NOT_SELF_CONTAINED", detail: "A rule uses 'inspection.door', which is not part of this library item." } } : ITEM) });
    const u = userEvent.setup();
    await u.type(await screen.findByLabelText("Section title"), "!");
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("inspection.door");
  });
  it("lists where it is used and restores an old revision into the editor", async () => {
    open();
    const u = userEvent.setup();
    await screen.findByLabelText("Section title");
    await u.click(screen.getByRole("tab", { name: /Used in/ }));
    expect(screen.getByText("pdi")).toBeInTheDocument();
    await u.click(screen.getByRole("tab", { name: "History" }));
    expect(screen.getByText("current")).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Restore revision 1" }));
    expect(await screen.findByLabelText("Section title")).toHaveValue("Old tyres");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();                // restoring is an unsaved edit
  });
});

describe("import and duplicate", () => {
  it("offers a new draft of the same form, or a copy under a new name", async () => {
    const calls = serve({ "promote/import": () => ({ form: 9, draft_version: 90, created: { form: true, library_items: 0 }, notes: ["Library field 'x' already exists here with different content"] }) });
    const u = userEvent.setup();
    shell(<ImportDialog bundle={{ schema: 2, form: { key: "pdi", name: "PDI", type: "custom" } }} forms={FORMS} onClose={() => {}} />);
    expect(screen.getByLabelText(/As a new draft of “PDI”/)).toBeChecked();
    expect(screen.queryByLabelText("Name of the new form")).toBeNull();
    await u.click(screen.getByLabelText("As a new form (a copy)"));
    expect(screen.getByLabelText("Name of the new form")).toHaveValue("PDI (copy)");
    expect(screen.getAllByLabelText("Key")[0]).toHaveValue("pdi_copy");
    await u.click(screen.getByRole("button", { name: "Import as a draft" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("as_new_key=pdi_copy"))).toBe(true));
    expect(calls.find((c) => c.url.includes("promote/import"))!.url).toContain("as_new_name=PDI+%28copy%29");
    expect(await screen.findByText(/A new form was created/)).toBeInTheDocument();
    expect(screen.getByText(/already exists here with different content/)).toBeInTheDocument();
  });
  it("imports a system form into its own place and an unknown form as new, and shows conflicts", async () => {
    serve({ "promote/import": () => ({ status: 400, body: { code: "IMPORT_CONFLICTS", detail: "x", conflicts: ["Form 'pdi' is a start form here"] } }) });
    const u = userEvent.setup();
    const { unmount } = shell(<ImportDialog bundle={{ schema: 2, form: { key: "whatever", name: "Start", type: "start" } }} forms={FORMS} onClose={() => {}} />);
    expect(screen.getByText(/replaces the content of the start form as a new draft/)).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    await u.click(screen.getByRole("button", { name: "Import as a draft" }));
    expect(await screen.findByText(/Form 'pdi' is a start form here/)).toBeInTheDocument();
    unmount();
    shell(<ImportDialog bundle={{ schema: 1, form: { key: "ev", name: "EV", kind: "inspection" } }} forms={FORMS} onClose={() => {}} />);
    expect(screen.getByText(/No form with the key “ev” exists here/)).toBeInTheDocument();
  });
  it("duplicates a form under a new key", async () => {
    const calls = serve({ "forms/1/duplicate": () => ({ form: 5, draft_version: 50, created: { form: true, library_items: 0 }, notes: [] }) });
    const u = userEvent.setup();
    shell(<DuplicateDialog form={FORMS[0]!} onClose={() => {}} />);
    await u.clear(screen.getByLabelText("Name of the copy"));
    await u.type(screen.getByLabelText("Name of the copy"), "PDI two");
    expect(screen.getByLabelText("Key")).toHaveValue("pdi_two");
    await u.click(screen.getByRole("button", { name: "Duplicate" }));
    await waitFor(() => expect(JSON.parse(String(calls.find((c) => c.url.includes("duplicate"))!.init!.body))).toEqual({ key: "pdi_two", name: "PDI two" }));
  });
});
