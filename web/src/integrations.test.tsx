import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import type { FormSummary, Integration } from "./api/types";
import {
  bodyText,
  insertValue,
  jsonOpenToken,
  matchValues,
  parseBody,
  parseParts,
  joinParts,
  EVENT_LABEL,
  integrationForms,
  pickerHint,
  removeValue,
  STARTER_BODY,
  type CatalogueEntry,
} from "./lib/integrationDef";
import { Integrations } from "./pages/admin/Integrations";
import { IntegrationEditor } from "./pages/admin/integrations/IntegrationEditor";
import { JsonEditor } from "./pages/admin/integrations/JsonEditor";
import { FieldChecklist } from "./pages/admin/integrations/Rows";
import { ValueInput } from "./pages/admin/integrations/ValueInput";
import { ToastProvider } from "./ui/kit";

afterEach(() => vi.restoreAllMocks());

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const ME = { id: 1, username: "a", name: "A", role: "admin", permissions: { "integrations.manage": "all" } };
type Handler = (init?: RequestInit, url?: string) => { status?: number; body: unknown } | unknown;
function serve(routes: Record<string, Handler>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    const hit = Object.entries(routes)
      .filter(([p]) => url.includes(p))
      .sort((a, b) => b[0].length - a[0].length)[0];
    if (!hit) return json({ detail: "not found" }, 404);
    const out = hit[1](init, url) as { status?: number; body?: unknown } | unknown;
    return out && typeof out === "object" && "body" in (out as object)
      ? json((out as { body: unknown }).body, (out as { status?: number }).status ?? 200)
      : json(out);
  });
  return calls;
}
/** A handler result that is the body itself (an Integration has its own "body" key). */
const ok = (body: unknown) => ({ body });
const shell = (ui: React.ReactNode, path = "/") =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <ToastProvider>{ui}</ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );

const CAT: CatalogueEntry[] = [
  { group: "booking", ref: "booking.customer_name", label: "Customer name", type: "text" },
  { group: "booking", ref: "booking.city", label: "City", type: "text" },
  { group: "inspection", ref: "inspection.odometer", label: "Odometer", type: "number" },
  { group: "job", ref: "job.booking_id", label: "Booking ID", type: "text" },
  { group: "link", ref: "link.pdf", label: "PDF link", type: "text" },
];
const FORMS: FormSummary[] = [
  {
    id: 1,
    key: "booking",
    type: "booking",
    name: "Booking",
    is_active: true,
    inspection_type: "",
    draft_version: null,
    published_version: { id: 5, number: 1 },
  },
  {
    id: 2,
    key: "pdi",
    type: "custom",
    name: "PDI",
    is_active: true,
    inspection_type: "pdi",
    draft_version: null,
    published_version: { id: 10, number: 1 },
  },
];
const INTEGRATION: Integration = {
  id: "i1",
  form: 2,
  form_key: "pdi",
  name: "CRM",
  event: "pdf.ready",
  method: "PUT",
  url: "https://crm.example.com/leads/{{job.booking_id}}",
  query: [{ key: "src", value: "vayu" }],
  headers: [{ key: "Authorization", value: "Bearer abc" }],
  body_mode: "custom",
  body: { ref: "{{job.booking_id}}", n: 3 },
  include_data: true,
  include_pdf: false,
  include_image_zip: false,
  include_video_zip: false,
  fields: [],
  is_active: true,
  broken_refs: [],
};
const PREVIEW = {
  method: "PUT",
  url: "https://crm.example.com/leads/SA1?src=vayu",
  headers: [
    { name: "Authorization", value: "Bearer abc" },
    { name: "Content-Type", value: "application/json" },
  ],
  body: '{\n  "ref": "SA1"\n}',
  sample: false,
  booking: "b1",
  broken_refs: [],
};

describe("values inside a text", () => {
  it("takes a text apart into text and values, and puts it back", () => {
    const s = "Inspection for {{booking.customer_name}} ({{ job.booking_id }})";
    expect(parseParts(s)).toEqual([
      { t: "Inspection for " },
      { r: "booking.customer_name" },
      { t: " (" },
      { r: "job.booking_id" },
      { t: ")" },
    ]);
    expect(joinParts(parseParts("plain"))).toBe("plain");
    expect(parseParts("")).toEqual([{ t: "" }]);
    expect(insertValue("ab", 0, 1, "job.booking_id")).toEqual({ value: "a{{job.booking_id}}b", focus: 2 });
    expect(insertValue("{{job.booking_id}}", 1, 0, "x.y").value).toBe("{{job.booking_id}}"); // a value part is not text
    expect(removeValue("a{{job.booking_id}}b", 1)).toBe("ab");
    expect(removeValue("a{{job.booking_id}}b", 0)).toBe("a{{job.booking_id}}b");
  });
  it("explains each event's values", () => {
    expect(pickerHint("booking", "booking.created")).toMatch(/choose an inspection form/);
    expect(pickerHint("custom", "booking.created")).toMatch(/Pick one of those events/);
    expect(pickerHint("custom", "booking.deleted")).toMatch(/Booking ID/);
    expect(pickerHint("custom", "inspection.started")).toMatch(/Check-in/);
    expect(pickerHint("custom", "inspection.submitted")).toMatch(/PDF link comes with/);
    expect(pickerHint("custom", "pdf.ready")).toBe("");
    expect(pickerHint("start", "checkin.completed")).toMatch(/every inspection type.*5 minutes.*offline/);
  });
  it("offers the booking, inspection and Check-in forms only", () => {
    const forms = ["booking", "custom", "start", "end"].map((type, id) => ({ id, type }));
    expect(integrationForms(forms).map((f) => f.type)).toEqual(["booking", "custom", "start"]);
  });
  it("finds the {{ the caret is in and the values that fit what was typed after it", () => {
    expect(jsonOpenToken('{ "a": "{{', 10)).toEqual({ start: 8, fragment: "" });
    expect(jsonOpenToken('{ "a": "x {{ inspection.odo', 27)).toEqual({ start: 10, fragment: "inspection.odo" });
    expect(jsonOpenToken('"{{job.booking_id | te', 22)).toEqual({ start: 1, fragment: "job.booking_id" });
    expect(jsonOpenToken('"{{job.booking_id}}" ', 21)).toBeNull(); // closed
    expect(jsonOpenToken('"{{ab" x', 8)).toBeNull(); // left the string
    expect(jsonOpenToken("{{a\nb", 5)).toBeNull(); // a new line
    expect(jsonOpenToken("no braces", 4)).toBeNull();
    expect(matchValues(CAT, "").length).toBe(CAT.length);
    expect(matchValues(CAT, "odo meter").map((e) => e.ref)).toEqual(["inspection.odometer"]);
    expect(matchValues(CAT, "booking id").map((e) => e.ref)).toEqual(["job.booking_id"]);
    expect(matchValues(CAT, "zzz")).toEqual([]);
  });
  it("tells valid JSON bodies from the rest, and shows a saved body as text", () => {
    expect(parseBody('{"a": 1}')).toEqual({ ok: true, body: { a: 1 } });
    expect(parseBody("[1, 2]")).toEqual({ ok: true, body: [1, 2] });
    expect(parseBody("5")).toMatchObject({ ok: false, error: expect.stringContaining("object") });
    expect(parseBody("null")).toMatchObject({ ok: false });
    expect(parseBody("{ nope")).toMatchObject({ ok: false });
    expect(parseBody("{ nope")).toHaveProperty("error");
    expect(bodyText({})).toBe("");
    expect(bodyText(null)).toBe("");
    expect(bodyText({ a: "{{job.id}}" })).toBe('{\n  "a": "{{job.id}}"\n}');
    expect(parseBody(STARTER_BODY).ok).toBe(true);
  });
});

function Holder({ start = "", onValue }: { start?: string; onValue?: (v: string) => void }) {
  const [v, setV] = useState(start);
  return (
    <ValueInput
      label="Value"
      value={v}
      catalogue={CAT}
      onChange={(x) => {
        setV(x);
        onValue?.(x);
      }}
    />
  );
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
    expect(screen.getAllByRole("textbox", { name: "Value" })[0]).toHaveValue("a"); // the braces are not kept
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

function Json({ start = "", onText }: { start?: string; onText?: (v: string) => void }) {
  const [v, setV] = useState(start);
  const p = parseBody(v);
  return (
    <JsonEditor
      value={v}
      catalogue={CAT}
      error={p.ok ? "" : p.error}
      onChange={(x) => {
        setV(x);
        onText?.(x);
      }}
    />
  );
}

describe("the JSON editor", () => {
  it("suggests the values of the form as {{ is typed, narrows them, and Enter picks", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Json start={'{\n  "x": "'} onText={seen} />);
    const box = screen.getByRole("textbox", { name: "Body (JSON)" });
    await u.click(box);
    await u.keyboard("{End}");
    await u.keyboard("{{{{");
    expect(await screen.findByRole("listbox", { name: "Suggestions" })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(CAT.length);
    await u.keyboard("odo");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    await u.keyboard("{Enter}");
    expect(seen).toHaveBeenLastCalledWith('{\n  "x": "{{inspection.odometer}}');
    expect(screen.queryByRole("listbox", { name: "Suggestions" })).toBeNull();
  });
  it("lists every value that fits, grouped, not just the first few", async () => {
    const u = userEvent.setup();
    const big: CatalogueEntry[] = [
      ...Array.from({ length: 20 }, (_, i) => ({ group: "booking", ref: `booking.f${i}`, label: `Field ${i}`, type: "text" })),
      ...Array.from({ length: 12 }, (_, i) => ({ group: "inspection", ref: `inspection.g${i}`, label: `Check ${i}`, type: "number" })),
    ];
    function Big() {
      const [v, setV] = useState('"');
      return <JsonEditor value={v} catalogue={big} error="" onChange={setV} />;
    }
    render(<Big />);
    await u.click(screen.getByRole("textbox", { name: "Body (JSON)" }));
    await u.keyboard("{End}{{{{");
    expect(screen.getAllByRole("option")).toHaveLength(32);
    expect(screen.getByText("Booking form")).toBeInTheDocument();
    expect(screen.getByText("Inspection")).toBeInTheDocument();
    await u.keyboard("check 1"); // narrows to Check 1, Check 10, Check 11
    expect(screen.getAllByRole("option").map((o) => o.getAttribute("title"))).toEqual([
      "inspection.g1",
      "inspection.g10",
      "inspection.g11",
    ]);
  });
  it("moves with the arrows, picks with Tab or a click, and Escape closes the suggestions", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Json start={'"'} onText={seen} />);
    await u.click(screen.getByRole("textbox", { name: "Body (JSON)" }));
    await u.keyboard("{End}{{{{");
    await u.keyboard("{ArrowDown}{ArrowDown}{ArrowUp}{Tab}");
    expect(seen).toHaveBeenLastCalledWith('"{{booking.city}}');
    await u.keyboard("{{{{");
    await u.keyboard("{Escape}");
    expect(screen.queryByRole("listbox", { name: "Suggestions" })).toBeNull();
    await u.keyboard("{Backspace}{Backspace}{{{{job");
    await u.click(await screen.findByRole("option", { name: /Booking ID/ }));
    expect(seen).toHaveBeenLastCalledWith('"{{booking.city}}{{job.booking_id}}');
  });
  it("adds a value at the caret with + value, quoting it when it is not inside a string", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Json start={'{ "a": '} onText={seen} />);
    await u.click(screen.getByRole("textbox", { name: "Body (JSON)" }));
    await u.keyboard("{End}");
    await u.click(screen.getByRole("button", { name: "+ value" }));
    await u.click(await screen.findByRole("option", { name: /Customer name/ }));
    expect(seen).toHaveBeenLastCalledWith('{ "a": "{{booking.customer_name}}"');
  });
  it("says what is wrong with the JSON, and Format tidies valid JSON", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    render(<Json start={'{"a":1'} onText={seen} />);
    expect(screen.getByTestId("json-error")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Format" })).toBeDisabled();
    await u.click(screen.getByRole("textbox", { name: "Body (JSON)" }));
    await u.keyboard("{End}}");
    expect(screen.queryByTestId("json-error")).toBeNull();
    await u.click(screen.getByRole("button", { name: "Format" }));
    expect(seen).toHaveBeenLastCalledWith('{\n  "a": 1\n}');
  });
});

describe("the field checklist", () => {
  it("lists the check-in answers instead of the inspection's on the Check-in form", async () => {
    const u = userEvent.setup();
    const cat = [...CAT, { group: "start", ref: "start.checkin_gps", label: "Check-in GPS", type: "text" }];
    render(<FieldChecklist fields={[]} catalogue={cat} parts={["booking", "start"]} onChange={() => {}} />);
    await u.click(screen.getByRole("button", { name: "Only these" }));
    expect(screen.getByRole("checkbox", { name: /Check-in GPS/ })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Odometer/ })).toBeNull();
  });
  it("sends everything, or only the ticked fields of the booking and inspection forms", async () => {
    const u = userEvent.setup();
    const seen = vi.fn();
    function Host() {
      const [f, setF] = useState<string[]>([]);
      return (
        <FieldChecklist
          fields={f}
          catalogue={CAT}
          onChange={(x) => {
            setF(x);
            seen(x);
          }}
        />
      );
    }
    render(<Host />);
    expect(screen.queryByRole("group", { name: "Fields" })).toBeNull();
    await u.click(screen.getByRole("button", { name: "Only these" }));
    expect(screen.getByText(/With none ticked, all are sent/)).toBeInTheDocument();
    expect(screen.queryByText("Booking ID")).toBeNull(); // job facts are not fields
    await u.click(screen.getByRole("checkbox", { name: /Customer name/ }));
    await u.click(screen.getByRole("checkbox", { name: /Odometer/ }));
    expect(seen).toHaveBeenLastCalledWith(["customer_name", "odometer"]);
    await u.type(screen.getByRole("searchbox", { name: "Search fields" }), "city");
    expect(screen.getByRole("checkbox", { name: /City/ })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Odometer/ })).toBeInTheDocument(); // ticked ones stay visible
    await u.click(screen.getByRole("button", { name: "All fields" }));
    expect(seen).toHaveBeenLastCalledWith([]);
  });
});

function editor(path: string, extra: Record<string, Handler> = {}) {
  const calls = serve({
    "auth/me": () => ME,
    forms: () => FORMS,
    "integrations/catalogue": () => CAT,
    "integrations/preview": () => ok(PREVIEW),
    // the server's table of which form may use which event
    "integrations/events": (_i, url) =>
      url!.includes("form=1")
        ? ["booking.created", "booking.updated", "booking.deleted"]
        : url!.includes("form=3")
          ? ["checkin.completed"]
          : Object.keys(EVENT_LABEL).filter((e) => e !== "checkin.completed"),
    ...extra,
  });
  shell(
    <Routes>
      <Route path="/integrations" element={<p>the list</p>} />
      <Route path="/integrations/:id" element={<IntegrationEditor />} />
    </Routes>,
    path,
  );
  return calls;
}
const sent = (calls: { url: string; init?: RequestInit }[], part: string) =>
  calls.filter((c) => c.url.includes(part) && c.init?.method !== "GET" && c.init?.body).map((c) => JSON.parse(String(c.init!.body)));

describe("the integration editor", () => {
  it("offers the Check-in form only its own event, without PDF or ZIP links", async () => {
    const u = userEvent.setup();
    const checkin = { ...FORMS[1]!, id: 3, key: "checkin", type: "start", name: "Check-in" } as FormSummary;
    editor("/integrations/new", { forms: () => [...FORMS, checkin] });
    await u.selectOptions(await screen.findByRole("combobox", { name: "Form" }), "3");
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Send when" })).toHaveValue("checkin.completed"));
    expect(within(screen.getByRole("combobox", { name: "Send when" })).getAllByRole("option")).toHaveLength(1);
    expect(screen.queryByRole("checkbox", { name: /PDF link/ })).toBeNull();
    expect(screen.getByRole("checkbox", { name: /check-in answers/ })).toBeChecked();
  });
  it("builds a request, shows the preview, and saves it cleaned", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new", {
      integrations: (init, url) =>
        init?.method === "POST" && !String(url).includes("preview") && !String(url).includes("catalogue")
          ? { status: 201, body: INTEGRATION }
          : [],
    });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "Name" }), "CRM");
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "PUT");
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/leads/");
    await u.click(screen.getByRole("button", { name: "Insert a value into URL" }));
    await u.click(await screen.findByRole("option", { name: /Booking ID/ }));
    await u.click(screen.getByRole("button", { name: /Add parameter/ }));
    await u.type(screen.getByRole("textbox", { name: "Parameter name 1" }), "src");
    await u.type(screen.getByRole("textbox", { name: "Parameter value 1" }), "vayu");
    await u.click(screen.getByRole("button", { name: /Add header/ })); // left half-built: not sent
    await u.click(screen.getByRole("button", { name: "Custom" }));
    const json = screen.getByRole("textbox", { name: "Body (JSON)" });
    expect(json).toHaveValue(STARTER_BODY); // a new custom body starts with an example
    await u.clear(json);
    await u.click(json);
    await u.paste('{"ref": "x", "n": [1, {"deep": "{{job.booking_id}}"}]}');
    expect(await screen.findByTestId("preview-request")).toHaveTextContent("PUT https://crm.example.com/leads/SA1?src=vayu");
    const previews = sent(calls, "integrations/preview");
    expect(previews.at(-1)).toMatchObject({
      form: 2,
      event: "pdf.ready",
      method: "PUT",
      url: "https://crm.example.com/leads/{{job.booking_id}}",
      query: [{ key: "src", value: "vayu" }],
      headers: [],
      body_mode: "custom",
      body: { ref: "x", n: [1, { deep: "{{job.booking_id}}" }] },
    });
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
    expect(screen.getByRole("combobox", { name: "Form" })).toHaveValue("2"); // an inspection form first: it offers the most values
    const options = (n: number) => waitFor(() => expect(within(when).getAllByRole("option")).toHaveLength(n));
    await options(9); // every event but the Check-in form's own
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "Booking");
    await options(3);
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "PDI");
    await options(9);
    expect(screen.getByRole("group", { name: "Body type" })).toBeInTheDocument();
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "GET");
    expect(screen.getByText("No body is sent with GET.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Body type" })).toBeNull();
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "DELETE");
    expect(screen.getByText("No body is sent with DELETE.")).toBeInTheDocument();
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "Booking");
    expect(screen.getByRole("combobox", { name: "Send when" })).toHaveValue("booking.created"); // pdf.ready is not a booking event
  });

  it("says in the value list why it is short: the form and the event decide what exists", async () => {
    const u = userEvent.setup();
    editor("/integrations/new");
    await screen.findByRole("textbox", { name: "Name" });
    await u.click(screen.getByRole("button", { name: "Insert a value into URL" }));
    expect(screen.queryByText(/only booking values/)).toBeNull(); // PDF ready: everything exists
    await u.keyboard("{Escape}");
    await u.selectOptions(screen.getByRole("combobox", { name: "Send when" }), "booking.created");
    await u.click(screen.getByRole("button", { name: "Insert a value into URL" }));
    expect(screen.getByText(/only booking-form answers, booking details and event details exist yet/)).toBeInTheDocument();
    await u.keyboard("{Escape}");
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "Booking");
    await u.click(screen.getByRole("button", { name: "Insert a value into URL" }));
    expect(screen.getByText(/choose an inspection form/)).toBeInTheDocument();
  });

  it("explains a refused value next to the preview instead of showing a blank", async () => {
    const u = userEvent.setup();
    editor("/integrations/new", {
      "integrations/preview": () => ({
        status: 400,
        body: { code: "UNKNOWN_VALUE", detail: "Header X uses booking.nope, which this form and event do not offer." },
      }),
    });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    expect(await screen.findByRole("alert")).toHaveTextContent("booking.nope");
  });

  it("shows sample values when the form has no job, and previews another job by its Booking ID", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new", {
      "integrations/preview": (init) => ok({ ...PREVIEW, sample: !JSON.parse(String(init?.body)).booking }),
      bookings: () => ({ count: 1, next: null, previous: null, results: [{ id: "b9", booking_id: "SA9" }] }),
    });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    expect(await screen.findByText(/Sample values: no booking exists yet/)).toBeInTheDocument();
    await u.type(screen.getByRole("textbox", { name: "Preview with booking" }), "SA9{Enter}");
    expect(await screen.findByText(/Values of SA9/)).toBeInTheDocument();
    expect(sent(calls, "integrations/preview").at(-1)).toMatchObject({ booking: "b9" });
    await u.clear(screen.getByRole("textbox", { name: "Preview with booking" }));
    await u.click(screen.getByRole("button", { name: "Use" }));
    expect(await screen.findByText(/Sample values/)).toBeInTheDocument();
  });

  it("tells when a booking is not found and warns about values the form lost", async () => {
    const u = userEvent.setup();
    editor("/integrations/new", {
      "integrations/preview": () => ok({ ...PREVIEW, broken_refs: ["inspection.gone"] }),
      bookings: () => ({ count: 0, next: null, previous: null, results: [] }),
    });
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://x.example.com/");
    expect(await screen.findByText(/inspection.gone, which the form no longer has/)).toBeInTheDocument();
    await u.type(screen.getByRole("textbox", { name: "Preview with booking" }), "NOPE{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("No booking found for “NOPE”.");
  });

  it("opens a saved integration for editing and shows the server's reason when saving fails", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/i1", {
      "integrations/i1": (init) =>
        init?.method === "PATCH"
          ? { status: 400, body: { code: "LOCKED_HEADER", detail: "Host is set by the system and cannot be changed." } }
          : ok(INTEGRATION),
    });
    expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("CRM");
    expect(screen.getByRole("combobox", { name: "Form" })).not.toBeDisabled(); // the form can be changed
    expect(screen.getByRole("combobox", { name: "Method" })).toHaveValue("PUT");
    expect(screen.getByRole("textbox", { name: "Parameter value 1" })).toHaveValue("vayu");
    expect((screen.getByRole("textbox", { name: "Body (JSON)" }) as HTMLTextAreaElement).value).toContain('"ref": "{{job.booking_id}}"');
    await u.click(screen.getByRole("checkbox", { name: "Active" }));
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Host is set by the system");
    expect(calls.some((c) => c.init?.method === "PATCH" && JSON.parse(String(c.init.body)).is_active === false)).toBe(true);
  });

  it("blocks Save and says why while the JSON is broken, and the preview keeps the last good body", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new");
    await screen.findByRole("textbox", { name: "Name" });
    await u.type(screen.getByRole("textbox", { name: "Name" }), "CRM");
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    await u.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    const json = screen.getByRole("textbox", { name: "Body (JSON)" });
    await u.clear(json);
    await u.click(json);
    await u.paste('{"a": ');
    expect(screen.getByTestId("json-error")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await waitFor(() => expect(sent(calls, "integrations/preview").length).toBeGreaterThan(0));
    await u.paste("1}");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await u.selectOptions(screen.getByRole("combobox", { name: "Method" }), "GET");
    expect(screen.queryByTestId("json-error")).toBeNull(); // no body is sent, so no body to check
  });

  it("changes the form of a saved integration, and the checklist lists every field of the form", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/i1", {
      "integrations/i1": (init) => (init?.method === "PATCH" ? ok(INTEGRATION) : ok({ ...INTEGRATION, body_mode: "standard", body: {} })),
    });
    await screen.findByRole("textbox", { name: "Name" });
    await u.click(screen.getByRole("button", { name: "Only these" }));
    expect(await screen.findByRole("checkbox", { name: /Odometer/ })).toBeInTheDocument(); // an inspection field, though the event is pdf.ready... and any event
    expect(calls.some((c) => c.url.includes("integrations/catalogue?form=2") && !c.url.includes("event="))).toBe(true);
    await u.selectOptions(screen.getByRole("combobox", { name: "Form" }), "Booking");
    expect(screen.getByRole("combobox", { name: "Send when" })).toHaveValue("booking.created");
    await u.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent(calls, "integrations/i1").at(-1)).toMatchObject({ form: 1, event: "booking.created" }));
  });

  it("copies an integration into a new one that starts switched off", async () => {
    editor("/integrations/new?copy=i1", { "integrations/i1": () => ok(INTEGRATION) });
    expect(await screen.findByRole("textbox", { name: "Name" })).toHaveValue("CRM (copy)");
    expect(screen.queryByRole("checkbox", { name: "Active" })).toBeNull(); // a new one has no Active switch yet
    expect(screen.getByRole("combobox", { name: "Method" })).toHaveValue("PUT");
    expect(screen.getByRole("combobox", { name: "Form" })).not.toBeDisabled();
  });

  it("builds a standard body with the field checklist", async () => {
    const u = userEvent.setup();
    const calls = editor("/integrations/new");
    await screen.findByRole("textbox", { name: "Name" });
    await u.click(screen.getByRole("button", { name: "Only these" }));
    await u.click(await screen.findByRole("checkbox", { name: /Customer name/ }));
    await u.click(screen.getByRole("checkbox", { name: /City/ }));
    await u.type(screen.getByRole("textbox", { name: "URL" }), "https://crm.example.com/");
    await waitFor(() =>
      expect(sent(calls, "integrations/preview").at(-1)).toMatchObject({
        body_mode: "standard",
        fields: ["customer_name", "city"],
        include_data: true,
      }),
    );
    await u.click(screen.getByRole("checkbox", { name: /Data \(booking/ }));
    expect(screen.queryByRole("group", { name: "Which fields" })).toBeNull();
  });
});

describe("the integrations list", () => {
  it("shows the event and method, flags lost fields, and opens the editor, a copy or the log", async () => {
    const u = userEvent.setup();
    serve({
      "auth/me": () => ME,
      forms: () => FORMS,
      integrations: () => [
        { ...INTEGRATION, broken_refs: ["inspection.gone"], is_active: false },
        { ...INTEGRATION, id: "i2", name: "B", broken_refs: ["a", "b"] },
      ],
    });
    shell(
      <Routes>
        <Route path="/integrations" element={<Integrations />} />
        <Route path="/integrations/new" element={<p>new page</p>} />
        <Route path="/integrations/:id" element={<p>edit page</p>} />
      </Routes>,
      "/integrations",
    );
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
    serve({
      "auth/me": () => ME,
      forms: () => FORMS,
      "integrations/i1/test": () => ({ status: "failed", error: "missing_path_value" }),
      integrations: () => [INTEGRATION],
    });
    shell(<Integrations />);
    await u.click(await screen.findByRole("button", { name: "Test" }));
    expect(await screen.findByText("Test failed: A value in the URL path was empty")).toBeInTheDocument();
  });
});
