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

export type Pdi = { formId: number; bookingFormId: number; startFormId: number; endFormId: number; templateId: number };

async function publish(api: APIRequestContext, formId: number): Promise<void> {
  const f = await json(await api.get(`forms/${formId}`));
  const v = await json(await api.get(`form-versions/${f.draft_version.id}`));
  await json(await api.post(`form-versions/${v.id}/publish`, { data: { row_version: v.row_version } }));
}

async function addFields(api: APIRequestContext, sectionId: number, fields: Record<string, unknown>[]) {
  for (const f of fields) await json(await api.post(`sections/${sectionId}/fields`, { data: f }));
}

/** The booking, start and end forms (they exist from the start) and a PDI custom form with a PDF template. */
export async function seedForms(): Promise<Pdi> {
  const admin = await apiAs("admin");
  const mk = async (body: Record<string, unknown>) => json(await admin.post("forms", { data: body }));
  const system = async (type: string) => (await json(await admin.get(`forms?type=${type}`))).results[0] as { id: number };
  const booking = await system("booking");
  await publish(admin, booking.id);
  const start = await system("start");
  await publish(admin, start.id);
  const end = await system("end");
  await publish(admin, end.id);
  const pdi = await mk({ key: "pdi", name: "PDI" });
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
  return { formId: pdi.id, bookingFormId: booking.id, startFormId: start.id, endFormId: end.id, templateId: t.id };
}

// a valid small JPEG
export const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q==",
  "base64");

async function sha256Hex(buf: Buffer): Promise<string> {
  const { createHash } = await import("node:crypto");
  return createHash("sha256").update(buf).digest("hex");
}

/** Uploads one file the way the browser does: initiate, PUT each part, complete. */
export async function uploadFile(expert: APIRequestContext, bookingId: string, fieldKey: string, kind: string, contentType: string, data: Buffer): Promise<string> {
  const init = await json(await expert.post("media/initiate", { data: { booking: bookingId, client_uuid: crypto.randomUUID(), field_key: fieldKey, kind, content_type: contentType, size: data.length, sha256: await sha256Hex(data), source: "camera" } }));
  const parts: { part_number: number; etag: string }[] = [];
  for (const p of init.parts) {
    const r = await fetch(p.url, { method: "PUT", body: new Uint8Array(data.subarray((p.part_number - 1) * init.part_size, p.part_number * init.part_size)) });
    parts.push({ part_number: p.part_number, etag: r.headers.get("etag")! });
  }
  const done = await json(await expert.post(`media/${init.id}/complete`, { data: { parts } }));
  if (done.status !== "verified") throw new Error(`upload not verified: ${done.status}`);
  return init.id as string;
}

export async function expertId(): Promise<number> {
  const admin = await apiAs("admin");
  const users = await json(await admin.get("users"));
  return (users.results ?? users).find((u: { username: string }) => u.username === "expert").id;
}

export type JobOptions = { bookingId: string; door?: string; photo?: boolean; odometer?: number; type?: string };

/** A booking taken all the way: created by Ops, assigned, started and submitted by the expert. */
export async function submittedJob(o: JobOptions): Promise<string> {
  const ops = await apiAs("ops");
  const expert = await apiAs("expert");
  const b = await json(await ops.post("bookings", { data: { answers: {
    booking_id: o.bookingId, customer_name: "Test Customer", customer_phone: "9876500099", address: "9 Test Street", city: "delhi",
    inspection_date: "2026-11-25", inspection_time: "09:30", inspection_type: o.type ?? "pdi", car_make_model: "maruti_victoris" } } }));
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: await expertId() } }));
  await json(await expert.post(`bookings/${b.id}/start`, { data: { client_uuid: crypto.randomUUID(), inspection_type: o.type ?? "pdi" } }));
  const selfie = await uploadFile(expert, b.id, "selfie", "photo", "image/jpeg", JPEG);
  const inspection: Record<string, unknown> = { chassis_no: "MA3YPKCSKTJ273129", door: o.door ?? "ok", odometer: o.odometer ?? 100 };
  if (o.photo) inspection.door_photo = [await uploadFile(expert, b.id, "door_photo", "photo", "image/jpeg", JPEG)];
  await json(await expert.post(`bookings/${b.id}/submit`, { data: { client_submission_uuid: crypto.randomUUID(), answers: { inspection, start: { selfie: [selfie] }, end: { taking_payment: false } } } }));
  return b.id as string;
}

export async function waitForReport(bookingId: string): Promise<{ url: string; verify_url: string; filename: string; stale: boolean; revision: number }> {
  const ops = await apiAs("ops");
  for (let i = 0; i < 60; i++) {
    const r = await ops.get(`bookings/${bookingId}/report`);
    if (r.ok()) { const j = await r.json(); if (j.status === "ready") return j; }
    await new Promise((res) => setTimeout(res, 500));
  }
  throw new Error("report never became ready");
}
