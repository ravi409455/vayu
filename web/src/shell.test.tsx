import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, explain, staleInfo } from "./api/client";
import { AuthProvider, useAuth } from "./auth";
import { homeFor, RequireAuth } from "./guards";
import { visibleNav } from "./Layout";
import { nextGrant } from "./pages/admin/Roles";
import { FieldEditor } from "./pages/admin/FieldEditor";
import { FormBuilder, PublishDialog } from "./pages/admin/FormBuilder";
import { AccessMatrix } from "./ui/AccessMatrix";
import type { FormField, Me } from "./api/types";

afterEach(() => vi.restoreAllMocks());

function meResponse(me: Partial<Me> | null) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    me ? new Response(JSON.stringify({ id: 1, username: "u", name: "U", permissions: {}, ...me }), { status: 200, headers: { "Content-Type": "application/json" } })
       : new Response(JSON.stringify({ detail: "no" }), { status: 401, headers: { "Content-Type": "application/json" } }));
}

function app(path: string, perm?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<p>LOGIN PAGE</p>} />
            <Route path="/change-password" element={<RequireAuth><p>CHANGE PASSWORD PAGE</p></RequireAuth>} />
            <Route path="/board" element={<p>BOARD</p>} />
            <Route path="/jobs" element={<p>JOBS</p>} />
            <Route path="/forms" element={<RequireAuth perm={perm}><p>FORMS PAGE</p></RequireAuth>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("route guards", () => {
  it("sends a signed-out visitor to the login page", async () => {
    meResponse(null);
    app("/forms");
    expect(await screen.findByText("LOGIN PAGE")).toBeInTheDocument();
  });
  it("forces a password change before anything else", async () => {
    meResponse({ role: "ops", must_change_password: true });
    app("/forms");
    expect(await screen.findByText("CHANGE PASSWORD PAGE")).toBeInTheDocument();
  });
  it("lets someone with the permission in, and sends others to their own home", async () => {
    meResponse({ role: "admin", permissions: { "forms.view": "all" } });
    app("/forms", "forms.view");
    expect(await screen.findByText("FORMS PAGE")).toBeInTheDocument();
    vi.restoreAllMocks();
    meResponse({ role: "expert", permissions: {} });
    app("/forms", "forms.view");
    expect(await screen.findByText("JOBS")).toBeInTheDocument();
  });
  it("each role has its own home", () => {
    expect([homeFor("expert"), homeFor("ops"), homeFor("admin")]).toEqual(["/jobs", "/today", "/forms"]);
  });
  it("navigation follows role and permissions", () => {
    const titles = (role: string, perms: string[]) => visibleNav(role, (p) => perms.includes(p)).flatMap((g) => g.items.map((i) => i.label));
    expect(titles("expert", [])).toEqual(["My leads"]);
    const ops = titles("ops", ["bookings.view", "dashboards.view", "forms.view"]);
    expect(ops).toEqual(["Today", "Bookings", "Needs you", "Dashboard"]);
    expect(ops).not.toContain("Users");
    expect(ops).not.toContain("My leads");
    expect(titles("admin", ["users.view", "roles.manage", "forms.view"])).toEqual(expect.arrayContaining(["Users", "Roles & permissions", "Forms"]));
  });
});

describe("error handling", () => {
  it("explains each kind of failure in plain words", () => {
    expect(explain(new ApiError(403, {}))).toMatch(/not allowed/);
    expect(explain(new ApiError(426, {}))).toMatch(/out of date/);
    expect(explain(new ApiError(429, {}))).toMatch(/Too many/);
    expect(explain(new ApiError(500, {}))).toMatch(/server had a problem/);
    expect(explain(new ApiError(400, { code: "X", detail: "Booking ID 'A' is already used." }))).toBe("Booking ID 'A' is already used.");
    expect(explain(new ApiError(400, { city: ["Not a valid choice."] }))).toBe("city: Not a valid choice.");
    expect(explain(new TypeError("network"))).toMatch(/connection/);
  });
  it("reads who changed a booking from a 409", () => {
    const e = new ApiError(409, { code: "STALE_BOOKING", detail: "x", changed_by: "priya", changed_at: "2026-11-23T10:00:00Z", changed_keys: ["city"], row_version: 4 });
    expect(staleInfo(e)).toEqual({ by: "priya", at: "2026-11-23T10:00:00Z", keys: ["city"], rowVersion: 4 });
    expect(staleInfo(new ApiError(409, { code: "DRAFT_EXISTS" }))).toBeNull();
    expect(staleInfo(new Error("x"))).toBeNull();
  });
  it("a 401 signs the person out and a 426 asks for a reload", async () => {
    const { setApiHandlers } = await import("./api/client");
    const onUnauthorized = vi.fn();
    const onUpgrade = vi.fn();
    setApiHandlers({ onUnauthorized, onUpgrade });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    await expect(api("x")).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 426, headers: { "Content-Type": "application/json" } }));
    await expect(api("x")).rejects.toMatchObject({ status: 426 });
    expect(onUpgrade).toHaveBeenCalledOnce();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    onUnauthorized.mockClear();
    await expect(api("auth/login", { body: {} })).rejects.toMatchObject({ status: 401 });
    expect(onUnauthorized).toHaveBeenCalledOnce();     // sign-in failures are 401 too: wrong password shows its own message
  });
  it("sends the CSRF token on writes only", async () => {
    document.cookie = "csrftoken=abc123";
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    await api("x");
    await api("x", { body: { a: 1 } });
    const [get, post] = spy.mock.calls.map((c) => (c[1]?.headers ?? {}) as Record<string, string>);
    expect(get?.["X-CSRFToken"]).toBeUndefined();
    expect(post?.["X-CSRFToken"]).toBe("abc123");
  });
});

describe("permission grid", () => {
  it("cycles off -> own -> all -> off for scoped permissions", () => {
    expect(nextGrant(true, undefined)).toBe("own");
    expect(nextGrant(true, "own")).toBe("all");
    expect(nextGrant(true, "all")).toBeUndefined();
    expect(nextGrant(false, undefined)).toBe("all");
    expect(nextGrant(false, "all")).toBeUndefined();
  });
});

const FIELD: FormField = {
  id: 1, section: 1, key: "door", label: "Door", helper_text: "", type: "single_choice", config: { options: [{ key: "ok", label: "OK" }] },
  required: false, required_if: null, show_if: null, visible: true, order: 0, is_system: false, access: {}, locked: false, library: null,
};
const noop = () => {};

describe("field editor", () => {
  it("shows the key and type as fixed text after the first save", () => {
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly={false} />);
    expect(screen.getByText("door")).toBeInTheDocument();
    expect(screen.queryByLabelText("Key")).toBeNull();
    expect(screen.queryByLabelText("Type")).toBeNull();
  });
  it("only lets you save once something changed, and sends the new label", async () => {
    const onSave = vi.fn();
    const u = userEvent.setup();
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={noop} readOnly={false} />);
    expect(screen.getByRole("button", { name: "Save field" })).toBeDisabled();
    await u.type(screen.getByLabelText("Label"), "!");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ label: "Door!" }));
  });
  it("a published (read-only) version cannot be edited", () => {
    render(<FieldEditor field={FIELD} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly />);
    expect(screen.queryByRole("button", { name: "Save field" })).toBeNull();
    expect(screen.getByLabelText("Label")).toBeDisabled();
  });
  it("a photo field chooses which camera the Android app opens (Back by default)", async () => {
    const onSave = vi.fn();
    const u = userEvent.setup();
    const photo: FormField = { ...FIELD, key: "selfie2", type: "photo", config: { max_count: 1 } };
    render(<FieldEditor field={photo} choices={[]} lists={[]} categories={[]} onSave={onSave} onDelete={noop} readOnly={false} />);
    expect(screen.getByLabelText("Camera")).toHaveValue("back");
    await u.selectOptions(screen.getByLabelText("Camera"), "front");
    await u.click(screen.getByRole("button", { name: "Save field" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ config: expect.objectContaining({ camera: "front" }) }));
  });
  it("an upload-only photo field has no camera choice", () => {
    const photo: FormField = { ...FIELD, key: "doc2", type: "photo", config: { capture: "upload" } };
    render(<FieldEditor field={photo} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly={false} />);
    expect(screen.queryByLabelText("Camera")).toBeNull();
  });
  it("system fields cannot be deleted or made optional", () => {
    render(<FieldEditor field={{ ...FIELD, is_system: true }} choices={[]} lists={[]} categories={[]} onSave={noop} onDelete={noop} readOnly={false} />);
    expect(screen.queryByRole("button", { name: "Delete field" })).toBeNull();
    expect(screen.queryByText("Always required")).toBeNull();
  });
});

describe("publish dialog", () => {
  it("lists blocking problems and hides the publish button", () => {
    render(<PublishDialog state={{ issues: [{ path: "fields.door", code: "X", message: "needs options" }], warnings: [], done: false }} onClose={noop} onPublish={noop} />);
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
    rerender(<PublishDialog state={{ issues: [], warnings: [{ path: "", code: "FIELD_NOT_IN_PDF", message: "Field 'odometer' is not shown in the PDF template." }], done: true }} onClose={noop} onPublish={noop} />);
    expect(screen.getByText("Published")).toBeInTheDocument();
    expect(screen.getByText(/odometer/)).toBeInTheDocument();
  });
});

describe("access matrix editor", () => {
  it("changes one cell and one whole row", async () => {
    const onChange = vi.fn();
    const u = userEvent.setup();
    render(<AccessMatrix value={{}} onChange={onChange} />);
    await u.selectOptions(screen.getByLabelText("expert Uploading"), "hidden");
    expect(onChange).toHaveBeenLastCalledWith({ expert: { submitted: "hidden" } });
    await u.selectOptions(screen.getByLabelText("ops all stages"), "view");
    const all = onChange.mock.lastCall![0] as Record<string, Record<string, string>>;
    expect(Object.values(all.ops!)).toEqual(Array(6).fill("view"));
  });
});

describe("identity changes clear what was cached", () => {
  function probe() {
    const qc = new QueryClient();
    qc.setQueryData(["bookings"], [{ customer: "private" }]);
    let auth!: ReturnType<typeof useAuth>;
    function Grab() {
      auth = useAuth();
      return null;
    }
    render(<QueryClientProvider client={qc}><AuthProvider><Grab /></AuthProvider></QueryClientProvider>);
    return { qc, get auth() { return auth; } };
  }
  it("logout clears everything even when the call fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (u) =>
      String(u).includes("auth/logout") ? new Response("{}", { status: 500, headers: { "Content-Type": "application/json" } })
        : new Response(JSON.stringify({ id: 1, username: "a", permissions: {}, role: "ops" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const p = probe();
    await screen.findByText((_, el) => el === null || true).catch(() => {});
    await vi.waitFor(() => expect(p.auth.me).not.toBeNull());
    await expect(p.auth.logout()).rejects.toBeInstanceOf(ApiError);
    expect(p.qc.getQueryData(["bookings"])).toBeUndefined();
    expect(p.qc.getQueryData(["me"])).toBeNull();
  });
  it("login starts from an empty cache and a 401 anywhere clears it", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ id: 2, username: "b", permissions: {}, role: "ops" }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const p = probe();
    await vi.waitFor(() => expect(p.auth.me).not.toBeNull());
    p.qc.setQueryData(["bookings"], ["old person's data"]);
    await p.auth.login("b", "pw");
    expect(p.qc.getQueryData(["bookings"])).toBeUndefined();
    p.qc.setQueryData(["bookings"], ["more"]);
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 401, headers: { "Content-Type": "application/json" } }));
    await expect(api("anything")).rejects.toMatchObject({ status: 401 });
    expect(p.qc.getQueryData(["bookings"])).toBeUndefined();
    expect(p.qc.getQueryData(["me"])).toBeNull();
  });
});

describe("shell v3", () => {
  it("names the server from its host, and shows nothing on production", async () => {
    const { envName } = await import("./ui/Logo");
    expect(envName("localhost")).toBe("Local");
    expect(envName("127.0.0.1")).toBe("Local");
    expect(envName("vayu.test")).toBe("Local");
    expect(envName("staging.vayu.carcid.in")).toBe("Staging");
    expect(envName("vayu-dev.example.com")).toBe("Staging");
    expect(envName("vayu.carcid.in")).toBeNull();
    expect(envName("devices.carcid.in")).toBeNull();
  });
  it("builds the breadcrumb from the path and what the page is showing", async () => {
    const { crumbsFor } = await import("./ui/TopBar");
    expect(crumbsFor("/bookings", "")).toEqual([{ label: "Bookings" }]);
    expect(crumbsFor("/booking/abc", "BK-1044")).toEqual([{ label: "Bookings", to: "/bookings" }, { label: "BK-1044" }]);
    expect(crumbsFor("/forms/7", "Used car")).toEqual([{ label: "Forms", to: "/forms" }, { label: "Used car" }]);
    expect(crumbsFor("/forms/7", "")).toEqual([{ label: "Forms", to: "/forms" }]);
    expect(crumbsFor("/nowhere", "x")).toEqual([]);
  });
});


describe("the form builder's publish button", () => {
  it("is not clickable until the draft's version has loaded (a click before that did nothing)", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => { release = r; });
    const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("auth/me")) return ok({ id: 1, username: "a", name: "A", role: "admin", permissions: { "forms.edit": "all", "forms.publish": "all", "forms.view": "all" } });
      if (url.includes("form-versions/7")) { await gate; return ok({ id: 7, form: 1, number: 2, status: "draft", published_at: null, row_version: 0, pages: [], checks: [] }); }
      if (url.endsWith("forms/1")) return ok({ id: 1, key: "pdi", type: "custom", name: "PDI", is_active: true, inspection_type: "pdi", draft_version: { id: 7, number: 2 }, published_version: { id: 6, number: 1 } });
      return ok([]);
    });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/forms/1"]}><AuthProvider><Routes><Route path="/forms/:id" element={<FormBuilder />} /></Routes></AuthProvider></MemoryRouter>
      </QueryClientProvider>);
    const publish = await screen.findByRole("button", { name: /Check & publish/ });
    expect(publish).toBeDisabled();
    release();
    await waitFor(() => expect(publish).toBeEnabled());
  });
});
