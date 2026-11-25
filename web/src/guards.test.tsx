import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { visibleNav } from "./Layout";
import type { Me } from "./api/types";
import { AuthProvider } from "./auth";
import { homeFor, RequireAuth } from "./guards";

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
