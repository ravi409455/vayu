// Test helpers that talk straight to the API (setup and checks), not through the screens.
import { request, type APIRequestContext, type Page } from "@playwright/test";

export const API = "http://localhost:8000/api/v1";
export const PASSWORD = "Passw0rd-e2e";

export async function apiAs(username: string): Promise<APIRequestContext> {
  const ctx = await request.newContext({ baseURL: API + "/" });
  const r = await ctx.post("auth/login", { data: { username, password: PASSWORD, client: "web" } });
  if (!r.ok()) throw new Error(`login ${username}: ${r.status()}`);
  const csrf = (await ctx.storageState()).cookies.find((c) => c.name === "csrftoken")?.value ?? "";
  const wrap = (m: "post" | "patch" | "put" | "delete" | "get") =>
    ((url: string, opts: { data?: unknown } = {}) => (ctx[m] as typeof ctx.post)(url, { ...opts, headers: { "X-CSRFToken": csrf } })) as typeof ctx.post;
  return new Proxy(ctx, { get: (t, p: string) => (["post", "patch", "put", "delete"].includes(p) ? wrap(p as "post") : (t as never)[p]) }) as APIRequestContext;
}

export async function json<T = any>(r: Awaited<ReturnType<APIRequestContext["post"]>>): Promise<T> {
  if (!r.ok()) throw new Error(`${r.url()} -> ${r.status()} ${await r.text()}`);
  return (await r.json()) as T;
}

export async function signIn(page: Page, username: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

export type Pdi = { formId: number; bookingFormId: number; opsFormId: number; templateId: number };

async function publish(api: APIRequestContext, formId: number): Promise<void> {
  const f = await json(await api.get(`forms/${formId}`));
  const v = await json(await api.get(`form-versions/${f.draft_version.id}`));
  await json(await api.post(`form-versions/${v.id}/publish`, { data: { row_version: v.row_version } }));
}

async function addFields(api: APIRequestContext, sectionId: number, fields: Record<string, unknown>[]) {
  for (const f of fields) await json(await api.post(`sections/${sectionId}/fields`, { data: f }));
}

/** Booking form, check-in & wrap-up form, and a PDI inspection form with a PDF template. */
export async function seedForms(): Promise<Pdi> {
  const admin = await apiAs("admin");
  const mk = async (body: Record<string, unknown>) => json(await admin.post("forms", { data: body }));
  const booking = await mk({ key: "booking", kind: "booking", name: "Booking" });
  await publish(admin, booking.id);
  const ops = await mk({ key: "checkin", kind: "ops", name: "Check-in and wrap-up" });
  const ov = await json(await admin.get(`form-versions/${ops.draft_version.id}`));
  await json(await admin.patch(`pages/${ov.pages[0].id}`, { data: { title: "Check-in" } }));
  await addFields(admin, ov.pages[0].sections[0].id, [
    { key: "checkin_gps", label: "Your location", type: "gps" },
    { key: "selfie", label: "Selfie at the car", type: "photo", config: { max_count: 1 } },
  ]);
  const wrapPage = await json(await admin.post(`form-versions/${ov.id}/pages`, { data: { title: "Wrap-up" } }));
  const wrapSec = await json(await admin.post(`pages/${wrapPage.id}/sections`, { data: { title: "Payment" } }));
  await addFields(admin, wrapSec.id, [
    { key: "payment_status", label: "Payment", type: "single_choice", required: true, config: { options: [{ key: "paid", label: "Taking payment" }, { key: "pay_later", label: "Pay later" }] } },
    { key: "payment_amount", label: "Amount", type: "currency", required_if: { "==": [{ var: "ops.payment_status" }, "paid"] }, show_if: { "==": [{ var: "ops.payment_status" }, "paid"] } },
    { key: "google_review", label: "Google review taken", type: "yes_no" },
  ]);
  await publish(admin, ops.id);
  const pdi = await mk({ key: "pdi", kind: "inspection", name: "PDI", inspection_type: "pdi" });
  const v = await json(await admin.get(`form-versions/${pdi.draft_version.id}`));
  const exterior = v.pages[0];
  await json(await admin.patch(`pages/${exterior.id}`, { data: { title: "Exterior" } }));
  const body = v.pages[0].sections[0];
  await json(await admin.patch(`sections/${body.id}`, { data: { title: "Body" } }));
  await addFields(admin, body.id, [
    { key: "door", label: "Driver front door", type: "single_choice", required: true, config: { options: [{ key: "ok", label: "OK" }, { key: "dent", label: "Dent", is_defect: true, severity: "minor" }] } },
    { key: "door_photo", label: "Door photo", type: "photo", config: { max_count: 2 }, required_if: { "==": [{ var: "inspection.door" }, "dent"] }, show_if: { "==": [{ var: "inspection.door" }, "dent"] } },
    { key: "odometer", label: "Odometer", type: "number", config: { unit: "km", min: 0 } },
    { key: "engine_rating", label: "Engine rating", type: "rating", config: { category: "exterior" } },
  ]);
  const page2 = await json(await admin.post(`form-versions/${v.id}/pages`, { data: { title: "Final" } }));
  const sec2 = await json(await admin.post(`pages/${page2.id}/sections`, { data: { title: "Notes" } }));
  await addFields(admin, sec2.id, [{ key: "remarks", label: "Remarks", type: "long_text" }]);
  await json(await admin.patch(`form-versions/${v.id}/rating-config`, { data: { config: { categories: [{ key: "exterior", label: "Exterior", sections: ["Body"] }] } } }));
  await publish(admin, pdi.id);
  const t = await json(await admin.post("pdf-templates", { data: { form: pdi.id } }));
  const tv = await json(await admin.get(`pdf-template-versions/${t.versions[0].id}`));
  const definition = { filename: "{booking_id}PDI.pdf", branding: { title: "PRE DELIVERY CAR INSPECTION REPORT", color: "#a62830" }, blocks: [
    { type: "cover", photo: "inspection.door_photo", rows: [{ label: "Booking ID", field: "booking.booking_id" }, { label: "Chassis Number", field: "inspection.chassis_no" }] },
    { type: "table", title: "Exterior", rows: [{ label: "Driver Front Door", field: "inspection.door" }, { label: "Odometer", field: "inspection.odometer" }] },
    { type: "ratings", title: "Overall Rating" },
    { type: "photos", title: "Photos", columns: 2, items: [{ field: "inspection.door_photo", index: 0, caption: "Door" }] },
  ] };
  const saved = await json(await admin.patch(`pdf-template-versions/${tv.id}`, { data: { definition, row_version: tv.row_version } }));
  await json(await admin.post(`pdf-template-versions/${tv.id}/publish`, { data: { row_version: saved.row_version } }));
  return { formId: pdi.id, bookingFormId: booking.id, opsFormId: ops.id, templateId: t.id };
}
