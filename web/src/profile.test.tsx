import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "./auth";
import type { User } from "./api/types";
import { Profile } from "./pages/Profile";
import { Users } from "./pages/admin/Users";
import { ThemeSync } from "./ThemeSync";
import { ExpertCell } from "./ui/ExpertCell";
import { ToastProvider } from "./ui/kit";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
beforeEach(() => document.documentElement.removeAttribute("data-theme"));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
type Handler = (init?: RequestInit) => { status?: number; body: unknown } | unknown;
function serve(routes: Record<string, Handler>) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, init });
    const hit = Object.entries(routes)
      .filter(([p]) => url.includes(p))
      .sort((a, b) => b[0].length - a[0].length)[0];
    if (!hit) return json({ detail: "not found" }, 404);
    const out = hit[1](init) as { status?: number; body?: unknown } | unknown;
    return out && typeof out === "object" && "body" in (out as object)
      ? json((out as { body: unknown }).body, (out as { status?: number }).status ?? 200)
      : json(out);
  });
  return calls;
}
const shell = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <ToastProvider>
          <AuthProvider>{ui}</AuthProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
const ME = {
  id: 5,
  username: "expert",
  name: "Ravi Expert",
  email: "r@x.in",
  phone: "+919876500111",
  role: "expert",
  permissions: {},
  theme: "light",
  avatar_url: null,
};

describe("the profile page", () => {
  it("shows the details as read-only text with a note about the Admin", async () => {
    serve({ "auth/me": () => ME });
    shell(<Profile />);
    const details = within(await screen.findByRole("region", { name: "Details" }));
    expect(details.getByText("Ravi Expert")).toBeInTheDocument();
    expect(details.getByText("+91 98765 00111")).toBeInTheDocument(); // shown grouped
    expect(details.getByText("Expert")).toBeInTheDocument();
    expect(details.getByText(/ask an Admin/)).toBeInTheDocument();
    expect(details.queryByRole("textbox")).toBeNull(); // nothing to edit
  });
  it("offers Remove picture only when there is a picture, and removes it", async () => {
    const calls = serve({
      "auth/me/picture": () => ({ ...ME, avatar_url: null }),
      "auth/me": () => ({ ...ME, avatar_url: "/api/v1/users/5/picture?v=1" }),
    });
    const u = userEvent.setup();
    shell(<Profile />);
    await u.click(await screen.findByRole("button", { name: "Remove picture" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("auth/me/picture") && c.init?.method === "DELETE")).toBe(true));
  });
  it("has no Remove button without a picture", async () => {
    serve({ "auth/me": () => ME });
    shell(<Profile />);
    expect(await screen.findByRole("button", { name: "Upload a picture" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove picture" })).toBeNull();
  });
  it("sends a chosen picture with PUT and says so", async () => {
    const calls = serve({ "auth/me/picture": () => ({ ...ME, avatar_url: "/api/v1/users/5/picture?v=1" }), "auth/me": () => ME });
    const u = userEvent.setup();
    shell(<Profile />);
    await screen.findByRole("button", { name: "Upload a picture" });
    await u.upload(screen.getByLabelText("Upload a picture", { selector: "input" }), new File(["x"], "me.jpg", { type: "image/jpeg" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("auth/me/picture") && c.init?.method === "PUT")).toBe(true));
    expect(await screen.findByText("Picture saved.")).toBeInTheDocument();
  });
  it("refuses a file that is too big or not a picture before sending anything", async () => {
    const calls = serve({ "auth/me": () => ME });
    const u = userEvent.setup({ applyAccept: false });
    shell(<Profile />);
    await screen.findByRole("button", { name: "Upload a picture" });
    const input = screen.getByLabelText("Upload a picture", { selector: "input" });
    await u.upload(input, new File(["x"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a picture");
    const big = new File(["x"], "big.jpg", { type: "image/jpeg" });
    Object.defineProperty(big, "size", { value: 6 * 1024 * 1024 });
    await u.upload(input, big);
    expect(await screen.findByRole("alert")).toHaveTextContent("5 MB");
    expect(calls.some((c) => c.init?.method === "PUT")).toBe(false);
  });
  it("shows the server's reason when it refuses a picture", async () => {
    serve({
      "auth/me/picture": () => ({ status: 400, body: { code: "INVALID_IMAGE", detail: "That file is not a usable picture." } }),
      "auth/me": () => ME,
    });
    const u = userEvent.setup();
    shell(<Profile />);
    await screen.findByRole("button", { name: "Upload a picture" });
    await u.upload(screen.getByLabelText("Upload a picture", { selector: "input" }), new File(["x"], "me.jpg", { type: "image/jpeg" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not a usable picture");
  });
  it("applies a chosen theme at once and saves it", async () => {
    const calls = serve({ "auth/me/profile": () => ({ ...ME, theme: "dark" }), "auth/me": () => ME });
    const u = userEvent.setup();
    shell(<Profile />);
    await u.click(await screen.findByRole("radio", { name: /Dark/ }));
    expect(document.documentElement.dataset.theme).toBe("dark"); // before the server answers
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("auth/me/profile"))).toBeTruthy());
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("auth/me/profile"))!.init!.body))).toEqual({ theme: "dark" });
    expect(screen.getByRole("radio", { name: /Light/ })).toBeChecked(); // until the server's answer comes back
  });
  it("puts the look back if saving the theme fails", async () => {
    serve({ "auth/me/profile": () => ({ status: 500, body: { detail: "boom" } }), "auth/me": () => ME });
    const u = userEvent.setup();
    shell(<Profile />);
    await u.click(await screen.findByRole("radio", { name: /Dark/ }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  });
  it("checks the two new passwords match before asking the server, and shows the server's words", async () => {
    const calls = serve({
      "auth/change-password": () => ({ status: 400, body: { old_password: ["Incorrect password."] } }),
      "auth/me": () => ME,
    });
    const u = userEvent.setup();
    shell(<Profile />);
    const form = within(await screen.findByRole("region", { name: "Password" }));
    await u.type(form.getByLabelText("Current password"), "old-pass-1");
    await u.type(form.getByLabelText("New password"), "New-pass-77");
    await u.type(form.getByLabelText("New password again"), "different");
    await u.click(form.getByRole("button", { name: "Change password" }));
    expect(await form.findByRole("alert")).toHaveTextContent("The two new passwords are different.");
    expect(calls.some((c) => c.url.includes("change-password"))).toBe(false);
    await u.clear(form.getByLabelText("New password again"));
    await u.type(form.getByLabelText("New password again"), "New-pass-77");
    await u.click(form.getByRole("button", { name: "Change password" }));
    expect(await form.findByRole("alert")).toHaveTextContent("old_password: Incorrect password.");
  });
  it("says other devices were signed out after a password change", async () => {
    serve({ "auth/change-password": () => ({ detail: "Password changed." }), "auth/me": () => ME });
    const u = userEvent.setup();
    shell(<Profile />);
    const form = within(await screen.findByRole("region", { name: "Password" }));
    await u.type(form.getByLabelText("Current password"), "old-pass-1");
    await u.type(form.getByLabelText("New password"), "New-pass-77");
    await u.type(form.getByLabelText("New password again"), "New-pass-77");
    await u.click(form.getByRole("button", { name: "Change password" }));
    expect(await screen.findByText(/Other devices were signed out/)).toBeInTheDocument();
    expect(form.getByLabelText("Current password")).toHaveValue("");
  });
});

describe("the theme follows the person", () => {
  const media = (dark: boolean) => {
    const listeners: (() => void)[] = [];
    vi.stubGlobal("matchMedia", () => ({
      matches: dark,
      addEventListener: (_: string, f: () => void) => listeners.push(f),
      removeEventListener: () => {},
    }));
    return listeners;
  };
  it("uses their saved theme once signed in, and Light when nobody is", async () => {
    media(false);
    serve({ "auth/me": () => ({ ...ME, theme: "dark" }) });
    const { unmount } = shell(<ThemeSync />);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    unmount();
    serve({ "auth/me": () => ({ status: 401, body: { detail: "no" } }) });
    shell(<ThemeSync />);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("light"));
  });
  it("follows the device for 'match my device', including when the device switches", async () => {
    const listeners = media(true);
    serve({ "auth/me": () => ({ ...ME, theme: "system" }) });
    shell(<ThemeSync />);
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(listeners.length).toBeGreaterThan(0);
    listeners.forEach((f) => f());
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});

describe("the Admin's Users screen", () => {
  const ADMIN = {
    id: 1,
    username: "admin",
    name: "Asha",
    role: "admin",
    permissions: { "users.view": "all", "users.manage": "all" },
    theme: "light",
  };
  const people: User[] = [
    {
      id: 5,
      username: "expert",
      name: "Ravi Expert",
      email: "",
      phone: "+919876500111",
      role: "expert",
      is_active: true,
      must_change_password: false,
      avatar_url: "/api/v1/users/5/picture?v=1",
    },
    {
      id: 6,
      username: "expert2",
      name: "Meera",
      email: "",
      phone: "",
      role: "expert",
      is_active: true,
      must_change_password: false,
      avatar_url: null,
    },
  ];
  const page = (calls: ReturnType<typeof serve>) => {
    void calls;
  };
  it("edits a phone, and removes a picture only for someone who has one", async () => {
    const calls = serve({
      "auth/me": () => ADMIN,
      "users/5/picture": () => ({}),
      "users/5": () => people[0],
      users: () => ({ count: 2, next: null, previous: null, results: people }),
    });
    page(calls);
    const u = userEvent.setup();
    shell(<Users />);
    await screen.findByText("Ravi Expert");
    const rows = screen.getAllByRole("row");
    await u.click(within(rows.find((r) => /Ravi Expert/.test(r.textContent ?? ""))!).getByText("Ravi Expert"));
    expect(screen.getByLabelText("Phone")).toHaveValue("+919876500111");
    await u.clear(screen.getByLabelText("Phone"));
    await u.type(screen.getByLabelText("Phone"), "98765 43210");
    await u.click(screen.getByRole("button", { name: "Remove picture" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("users/5/picture") && c.init?.method === "DELETE")).toBe(true));
    expect(await screen.findByText(/initials show instead/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove picture" })).toBeNull();
    await u.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("users/5") && c.init?.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.url.endsWith("users/5") && c.init?.method === "PATCH")!.init!.body)).phone).toBe(
      "98765 43210",
    );
  });
  it("has no Remove picture for someone without one, and shows a phone error from the server", async () => {
    serve({
      "auth/me": () => ADMIN,
      "users/6": (init) =>
        init?.method === "PATCH" ? { status: 400, body: { phone: ["Enter a 10-digit Indian mobile number."] } } : people[1],
      users: () => ({ count: 2, next: null, previous: null, results: people }),
    });
    const u = userEvent.setup();
    shell(<Users />);
    await screen.findByText("Meera");
    const rows = screen.getAllByRole("row");
    await u.click(within(rows.find((r) => /Meera/.test(r.textContent ?? ""))!).getByText(/Meera/));
    expect(screen.queryByRole("button", { name: "Remove picture" })).toBeNull();
    await u.type(screen.getByLabelText("Phone"), "123");
    await u.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/10-digit Indian mobile/)).toBeInTheDocument();
  });
});

describe("the expert in a list", () => {
  const experts = [
    { id: 5, username: "expert", name: "Ravi Expert", avatar_url: "/api/v1/users/5/picture?v=1" },
    { id: 6, username: "expert2", name: "", avatar_url: null },
  ] as User[];
  it("shows their picture or initials with their name, a dash for nobody, and #id for someone unknown", () => {
    const { rerender } = render(<ExpertCell id={5} experts={experts} />);
    expect(screen.getByAltText("Picture of Ravi Expert")).toBeInTheDocument();
    expect(screen.getByText("Ravi Expert")).toBeInTheDocument();
    rerender(<ExpertCell id={6} experts={experts} />);
    expect(screen.getByText("expert2")).toBeInTheDocument();
    rerender(<ExpertCell id={null} experts={experts} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    rerender(<ExpertCell id={99} experts={experts} />);
    expect(screen.getByText("#99")).toBeInTheDocument();
  });
});
