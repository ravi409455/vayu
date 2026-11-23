import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import type { FormSummary, Integration } from "./api/types";
import { asKind, blankRow, cleanRows, eventsFor, insertValue, joinParts, parseParts, removeValue, typedFixed, type CatalogueEntry } from "./lib/integrationDef";
import { Integrations } from "./pages/admin/Integrations";
import { BodyBuilder } from "./pages/admin/integrations/BodyBuilder";
import { IntegrationEditor } from "./pages/admin/integrations/IntegrationEditor";
import { FieldChecklist } from "./pages/admin/integrations/Rows";
import { ValueInput } from "./pages/admin/integrations/ValueInput";
import { ToastProvider } from "./ui/kit";

afterEach(() => vi.restoreAllMocks());

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const ME = { id: 1, username: "a", name: "A", role: "admin", permissions: { "integrations.manage": "all" } };
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
/** A handler result that is the body itself (an Integration has its own "body" key). */
const ok = (body: unknown) => ({ body });
const shell = (ui: React.ReactNode, path = "/") => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}><AuthProvider><ToastProvider>{ui}</ToastProvider></AuthProvider></MemoryRouter>
  </QueryClientProvider>);

const CAT: CatalogueEntry[] = [
  { group: "booking", ref: "booking.customer_name", label: "Customer name", type: "text" },
  { group: "booking", ref: "booking.city", label: "City", type: "text" },
  { group: "inspection", ref: "inspection.odometer", label: "Odometer", type: "number" },
  { group: "job", ref: "job.booking_id", label: "Booking ID", type: "text" },
  { group: "link", ref: "link.pdf", label: "PDF link", type: "text" },
];
const FORMS: FormSummary[] = [
  { id: 1, key: "booking", type: "booking", name: "Booking", is_active: true, inspection_type: "", draft_version: null, published_version: { id: 5, number: 1 } },
  { id: 2, key: "pdi", type: "custom", name: "PDI", is_active: true, inspection_type: "pdi", draft_version: null, published_version: { id: 10, number: 1 } },
];
const INTEGRATION: Integration = {
  id: "i1", form: 2, form_key: "pdi", name: "CRM", event: "pdf.ready", method: "PUT", url: "https://crm.example.com/leads/{{job.booking_id}}",
  query: [{ key: "src", value: "vayu" }], headers: [{ key: "Authorization", value: "Bearer abc" }], body_mode: "custom",
  body: { rows: [{ key: "ref", value: "{{job.booking_id}}" }, { key: "n", fixed: 3 }] },
  include_data: true, include_pdf: false, include_image_zip: false, include_video_zip: false, fields: [], is_active: true, broken_refs: [],
};
const PREVIEW = { method: "PUT", url: "https://crm.example.com/leads/SA1?src=vayu", headers: [{ name: "Authorization", value: "Bearer abc" }, { name: "Content-Type", value: "application/json" }], body: '{\n  "ref": "SA1"\n}', sample: false, booking: "b1", broken_refs: [] };

describe("values inside a text", () => {
  it("takes a text apart into text and values, and puts it back", () => {
    const s = "Inspection for {{booking.customer_name}} ({{ job.booking_id }})";
    expect(parseParts(s)).toEqual([{ t: "Inspection for " }, { r: "booking.customer_name" }, { t: " (" }, { r: "job.booking_id" }, { t: ")" }]);
    expect(joinParts(parseParts("plain"))).toBe("plain");
    expect(parseParts("")).toEqual([{ t: "" }]);
    expect(insertValue("ab", 0, 1, "job.booking_id")).toEqual({ value: "a{{job.booking_id}}b", focus: 2 });
    expect(insertValue("{{job.booking_id}}", 1, 0, "x.y").value).toBe("{{job.booking_id}}");      // a value part is not text
    expect(removeValue("a{{job.booking_id}}b", 1)).toBe("ab");
    expect(removeValue("a{{job.booking_id}}b", 0)).toBe("a{{job.booking_id}}b");
  });
  it("offers the booking events to a booking form and all nine to an inspection form", () => {
    expect(eventsFor("booking")).toEqual(["booking.created", "booking.updated", "booking.deleted"]);
    expect(eventsFor("custom")).toHaveLength(9);
  });
  it("types a fixed value, leaves half-built rows out, and changes a row's kind", () => {
    expect(typedFixed("number", "")).toBe(0);
    expect(typedFixed("number", "12")).toBe(12);
    expect(typedFixed("yesno", "true")).toBe(true);
    expect(typedFixed("text", "x")).toBe("x");
    expect(cleanRows([{ key: " ", value: "x" }, { key: "a", value: "{{x.y}}", as_text: true }, { key: "g", rows: [{ key: "", fixed: 1 }, { key: "n", fixed: 2 }] }]))
      .toEqual([{ key: "a", value: "{{x.y}}", as_text: true }, { key: "g", rows: [{ key: "n", fixed: 2 }] }]);
    expect(asKind({ key: "k", value: "v" }, "group")).toEqual({ key: "k", rows: [] });
    expect(blankRow("fixed")).toEqual({ key: "", fixed: "" });
  });
});

function Holder({ start = "", onValue }: { start?: string; onValue?: (v: string) => void }) {
  const [v, setV] = useState(start);
  return <ValueInput label="Value" value={v} catalogue={CAT} onChange={(x) => { setV(x); onValue?.(x); }} />;
}

describe("the value input", () => {
  it("adds a value from the searchable list and shows it as a chip", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Holder onValue={seen} />);
    await u.type(screen.getByRole("textbox", { name: "Value" }), "Hi ");
    await u.click(screen.getByRole("button", { name: "Insert a value into Value" }));
    await u.type(screen.getByRole("searchbox", { name: "Search values" }), "custo");
    expect(screen.queryByRole("option", { name: /Odometer/ })).toBeNull();
    await u.click(screen.getByRole("option", { name: /Customer name/ }));
    expect(seen).toHaveBeenLastCalledWith("Hi {{booking.customer_name}}");
    expect(screen.getByText("Customer name")).toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });
  it("opens the list when {{ is typed, and Enter takes the first match", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Holder onValue={seen} />);
    await u.type(screen.getByRole("textbox", { name: "Value" }), "a{{{{");
    const search = screen.getByRole("searchbox", { name: "Search values" });
    expect(screen.getAllByRole("textbox", { name: "Value" })[0]).toHaveValue("a");               // the braces are not kept
    await u.type(search, "odo{Enter}");
    expect(seen).toHaveBeenLastCalledWith("a{{inspection.odometer}}");
  });
  it("keeps a pasted {{value}} as a chip instead of opening the list", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Holder onValue={seen} />);
    await u.click(screen.getByRole("textbox", { name: "Value" }));
    await u.paste("id {{job.booking_id}}");
    expect(seen).toHaveBeenLastCalledWith("id {{job.booking_id}}");
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.getByRole("button", { name: "Remove Booking ID" })).toBeInTheDocument();
  });
  it("closes the list with Escape or by clicking away, and says when nothing matches", async () => {
    const u = userEvent.setup();
    render(<Holder />);
    await u.click(screen.getByRole("button", { name: "Insert a value into Value" }));
    await u.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText(/Nothing matches/)).toBeInTheDocument();
    await u.keyboard("{Escape}");
    expect(screen.queryByRole("searchbox")).toBeNull();
    await u.click(screen.getByRole("button", { name: "Insert a value into Value" }));
    await u.click(document.body);
    expect(screen.queryByRole("searchbox")).toBeNull();
  });
  it("removes a value with its × or with Backspace right after it", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Holder start="a{{booking.city}}b{{job.booking_id}}" onValue={seen} />);
    await u.click(screen.getByRole("button", { name: "Remove City" }));
    expect(seen).toHaveBeenLastCalledWith("ab{{job.booking_id}}");
    const boxes = screen.getAllByRole("textbox", { name: "Value" });
    boxes[boxes.length - 1]!.focus();
    await u.keyboard("{Backspace}");
    expect(seen).toHaveBeenLastCalledWith("ab");
  });
  it("shows a value that the form no longer offers in warning colours", () => {
    render(<Holder start="{{inspection.gone}}" />);
    expect(screen.getByTitle(/is not offered/)).toHaveClass("gone");
  });
});

function Rows({ start = [] as ReturnType<typeof blankRow>[], onRows }: { start?: ReturnType<typeof blankRow>[]; onRows?: (r: unknown) => void }) {
  const [rows, setRows] = useState(start);
  return <BodyBuilder rows={rows} catalogue={CAT} onChange={(r) => { setRows(r); onRows?.(r); }} />;
}

describe("the body builder", () => {
  it("builds named rows from values, fixed values and nested groups", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Rows onRows={seen} />);
    await u.click(screen.getByRole("button", { name: /Add row/ }));
    await u.type(screen.getByRole("textbox", { name: "Key 1" }), "ref");
    await u.click(screen.getByRole("button", { name: "Insert a value into Value 1" }));
    await u.click(screen.getByRole("option", { name: /Booking ID/ }));
    await u.click(screen.getByRole("checkbox", { name: "Send as text 1" }));
    await u.click(screen.getByRole("button", { name: /Add group/ }));
    await u.type(screen.getByRole("textbox", { name: "Key 2" }), "car");
    const group = screen.getByRole("textbox", { name: "Key 2" }).closest(".brow") as HTMLElement;
    await u.click(within(group).getByRole("button", { name: /Add row/ }));
    await u.type(screen.getByRole("textbox", { name: "Key 2.1" }), "n");
    await u.selectOptions(screen.getByRole("combobox", { name: "Row type 2.1" }), "fixed");
    await u.selectOptions(screen.getByRole("combobox", { name: "Fixed type 2.1" }), "number");
    await u.type(screen.getByRole("spinbutton", { name: "Fixed value 2.1" }), "7");
    expect(cleanRows(seen.mock.lastCall![0])).toEqual([
      { key: "ref", value: "{{job.booking_id}}", as_text: true },
      { key: "car", rows: [{ key: "n", fixed: 7 }] }]);
    await u.selectOptions(screen.getByRole("combobox", { name: "Fixed type 2.1" }), "yesno");
    await u.selectOptions(screen.getByRole("combobox", { name: "Fixed value 2.1" }), "No");
    expect(cleanRows(seen.mock.lastCall![0])[1]).toEqual({ key: "car", rows: [{ key: "n", fixed: false }] });
    await u.click(screen.getByRole("button", { name: "Remove row 2.1" }));
    await u.click(screen.getByRole("button", { name: "Remove row 1" }));
    expect(cleanRows(seen.mock.lastCall![0])).toEqual([{ key: "car", rows: [] }]);
  });
  it("stops nesting at the deepest level", () => {
    let rows: ReturnType<typeof blankRow>[] = [{ key: "leaf", fixed: 1 }];
    for (let i = 0; i < 5; i++) rows = [{ key: `n${i}`, rows }];
    render(<Rows start={rows} />);
    expect(screen.getAllByRole("button", { name: /Add group/ })).toHaveLength(5);                 // the sixth level has none
  });
});

describe("the field checklist", () => {
  it("sends everything, or only the ticked fields of the booking and inspection forms", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    function Host() {
      const [f, setF] = useState<string[]>([]);
      return <FieldChecklist fields={f} catalogue={CAT} onChange={(x) => { setF(x); seen(x); }} />;
    }
    render(<Host />);
    expect(screen.queryByRole("group", { name: "Fields" })).toBeNull();
    await u.click(screen.getByRole("button", { name: "Only these" }));
    expect(seen).toHaveBeenLastCalledWith(["customer_name"]);
    expect(screen.queryByText("Booking ID")).toBeNull();                                           // job facts are not fields
    await u.click(screen.getByRole("checkbox", { name: /Odometer/ }));
    expect(seen).toHaveBeenLastCalledWith(["customer_name", "odometer"]);
    await u.type(screen.getByRole("searchbox", { name: "Search fields" }), "city");
    expect(screen.getByRole("checkbox", { name: /City/ })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Odometer/ })).toBeInTheDocument();             // ticked ones stay visible
    await u.click(screen.getByRole("button", { name: "All fields" }));
    expect(seen).toHaveBeenLastCalledWith([]);
  });
});

function editor(path: string, extra: Record<string, Handler> = {}) {
  const calls = serve({
    "auth/me": () => ME, "forms": () => FORMS, "integrations/catalogue": () => CAT, "integrations/preview": () => ok(PREVIEW), ...extra,
  });
  shell(<Routes><Route path="/integrations" element={<p>the list</p>} /><Route path="/integrations/:id" element={<IntegrationEditor />} /></Routes>, path);
  return calls;
}
const sent = (calls: { url: string; init?: RequestInit }[], part: string) => calls.filter((c) => c.url.includes(part) && c.init?.method !== "GET" && c.init?.body).map((c) => JSON.parse(String(c.init!.body)));

describe("the integration editor", () => {
  it("builds a request, shows the preview, and saves it cleaned", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new", { "integrations": (init, url) => (init?.method === "POST" && !String(url).includes("preview") && !String(url).includes("catalogue") ? { status: 201, body: INTEGRATION } : []) });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "Name" }), "CRM");
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "PUT");
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/leads/");
    await u.click(screen.getByRole("button", { name: "Insert a value into URL" }));
    await u.click(await screen.findByRole("option", { name: /Booking ID/ }));
    await u.click(screen.getByRole("button", { name: /Add parameter/ }));
    await u.type(screen.getByRole("textbox", { name: "Parameter name 1" }), "src");
    await u.type(screen.getByRole("textbox", { name: "Parameter value 1" }), "vayu");
    await u.click(screen.getByRole("button", { name: /Add header/ }));                              // left half-built: not sent
    await u.click(screen.getByRole("button", { name: "Custom" }));
    await u.click(screen.getByRole("button", { name: /Add row/ }));
    await u.type(screen.getByRole("textbox", { name: "Key 1" }), "ref");
    await u.type(screen.getByRole("textbox", { name: "Value 1" }), "x");
    expect(await screen.findByTestId("preview-request")).toHaveTextContent("PUT https://crm.example.com/leads/SA1?src=vayu");
    const previews = sent(calls, "integrations/preview");
    expect(previews.at(-1)).toMatchObject({ form: 1, event: "booking.created", method: "PUT", url: "https://crm.example.com/leads/{{job.booking_id}}", query: [{ key: "src", value: "vayu" }], headers: [], body_mode: "custom", body: { rows: [{ key: "ref", value: "x" }] } });
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("the list")).toBeInTheDocument();
    const saved = calls.filter((c) => c.url.endsWith("/integrations") && c.init?.method === "POST");
    expect(saved).toHaveLength(1);
    expect(JSON.parse(String(saved[0]!.init!.body))).toMatchObject({ name: "CRM", headers: [], query: [{ key: "src", value: "vayu" }] });
  });

  it("offers a booking form's integration the booking events only, and hides the body for GET and DELETE", async () => {
    const u = userEvent.setup();
    editor("/integrations/new");
    await screen.findByRole("textbox", { name: "Name" });
    const when = screen.getByRole("combobox", { name: "Send when" });
    expect(within(when).getAllByRole("option")).toHaveLength(3);
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "PDI");
    expect(within(when).getAllByRole("option")).toHaveLength(9);
    expect(screen.getByRole("group", { name: "Body type" })).toBeInTheDocument();
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "GET");
    expect(screen.getByText("No body is sent with GET.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Body type" })).toBeNull();
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "DELETE");
    expect(screen.getByText("No body is sent with DELETE.")).toBeInTheDocument();
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "Booking");
    expect(screen.getByRole("combobox", { name: "Send when" })).toHaveValue("booking.created");   // pdf.ready is not a booking event
  });

  it("explains a refused value next to the preview instead of showing a blank", async () => {
    const u = userEvent.setup();
    editor("/integrations/new", { "integrations/preview": () => ({ status: 400, body: { code: "UNKNOWN_VALUE", detail: "Header X uses booking.nope, which this form and event do not offer." } }) });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    expect(await screen.findByRole("alert")).toHaveTextContent("booking.nope");
  });

  it("shows sample values when the form has no job, and previews another job by its Booking ID", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new", {
      "integrations/preview": (init) => ok({ ...PREVIEW, sample: !JSON.parse(String(init?.body)).booking }),
      "bookings": () => ({ count: 1, next: null, previous: null, results: [{ id: "b9", booking_id: "SA9" }] }),
    });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    expect(await screen.findByText(/Sample values: no job exists yet/)).toBeInTheDocument();
    await u.type(screen.getByRole("textbox", { name: "Preview with booking" }), "SA9{Enter}");
    expect(await screen.findByText(/Values of SA9/)).toBeInTheDocument();
    expect(sent(calls, "integrations/preview").at(-1)).toMatchObject({ booking: "b9" });
    await u.clear(screen.getByRole("textbox", { name: "Preview with booking" }));
    await u.click(screen.getByRole("button", { name: "Use" }));
    expect(await screen.findByText(/Sample values/)).toBeInTheDocument();
  });

  it("tells when a booking is not found and warns about values the form lost", async () => {
    const u = userEvent.setup();
    editor("/integrations/new", { "integrations/preview": () => ok({ ...PREVIEW, broken_refs: ["inspection.gone"] }), "bookings": () => ({ count: 0, next: null, previous: null, results: [] }) });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://x.example.com/");
    expect(await screen.findByText(/inspection.gone, which the form no longer has/)).toBeInTheDocument();
    await u.type(screen.getByRole("textbox", { name: "Preview with booking" }), "NOPE{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("No booking found for “NOPE”.");
  });

  it("opens a saved integration for editing and shows the server's reason when saving fails", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/i1", {
      "integrations/i1": (init) => (init?.method === "PATCH" ? { status: 400, body: { code: "LOCKED_HEADER", detail: "Host is set by the system and cannot be changed." } } : ok(INTEGRATION)),
    });
    expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("CRM");
    expect(screen.getByRole("combobox", { name: "Form" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Method" })).toHaveValue("PUT");
    expect(screen.getByRole("textbox", { name: "Parameter value 1" })).toHaveValue("vayu");
    expect(screen.getByRole("textbox", { name: "Key 1" })).toHaveValue("ref");
    await u.click(screen.getByRole("checkbox", { name: "Active" }));
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Host is set by the system");
    expect(calls.some((c) => c.init?.method === "PATCH" && JSON.parse(String(c.init.body)).is_active === false)).toBe(true);
  });

  it("copies an integration into a new one that starts switched off", async () => {
    editor("/integrations/new?copy=i1", { "integrations/i1": () => ok(INTEGRATION) });
    expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("CRM (copy)");
    expect(screen.queryByRole("checkbox", { name: "Active" })).toBeNull();                          // a new one has no Active switch yet
    expect(screen.getByRole("combobox", { name: "Method" })).toHaveValue("PUT");
    expect(screen.getByRole("combobox", { name: "Form" })).not.toBeDisabled();
  });

  it("builds a standard body with the field checklist", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new");
    await screen.findByRole("textbox", { name: "Name" });
    await u.click(screen.getByRole("button", { name: "Only these" }));
    await u.click(screen.getByRole("checkbox", { name: /City/ }));
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    await waitFor(() => expect(sent(calls, "integrations/preview").at(-1)).toMatchObject({ body_mode: "standard", fields: ["customer_name", "city"], include_data: true }));
    await u.click(screen.getByRole("checkbox", { name: /Data \(booking/ }));
    expect(screen.queryByRole("group", { name: "Which fields" })).toBeNull();
  });
});

describe("the integrations list", () => {
  it("shows the event and method, flags lost fields, and opens the editor, a copy or the log", async () => {
    const u = userEvent.setup();
    serve({ "auth/me": () => ME, "forms": () => FORMS, "integrations": () => [{ ...INTEGRATION, broken_refs: ["inspection.gone"], is_active: false }, { ...INTEGRATION, id: "i2", name: "B", broken_refs: ["a", "b"] }] });
    shell(<Routes><Route path="/integrations" element={<Integrations />} /><Route path="/integrations/new" element={<p>new page</p>} /><Route path="/integrations/:id" element={<p>edit page</p>} /></Routes>, "/integrations");
    expect(await screen.findAllByText("PDF ready")).toHaveLength(2);
    expect(screen.getAllByText(/PUT https:\/\/crm.example.com/, { selector: ".cell-sub" })).toHaveLength(2);
    expect(screen.getByText("Off")).toBeInTheDocument();
    expect(screen.getByText("Uses 1 field that no longer exists")).toBeInTheDocument();
    expect(screen.getByText("Uses 2 fields that no longer exist")).toBeInTheDocument();
    await u.click(screen.getByRole("button", { name: "Actions for CRM" }));
    await u.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(await screen.findByText("edit page")).toBeInTheDocument();
  });
  it("sends a test and says what happened", async () => {
    const u = userEvent.setup();
    serve({ "auth/me": () => ME, "forms": () => FORMS, "integrations/i1/test": () => ({ status: "failed", error: "missing_path_value" }), "integrations": () => [INTEGRATION] });
    shell(<Integrations />);
    await u.click(await screen.findByRole("button", { name: "Test" }));
    expect(await screen.findByText("Test failed: A value in the URL path was empty")).toBeInTheDocument();
  });
});
