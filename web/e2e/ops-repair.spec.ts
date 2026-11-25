import { expect, test } from "@playwright/test";
import { apiAs, JPEG, json, signIn, submittedJob, uploadFile, waitForReport } from "./api";

// F-168: the two Ops journeys the review found untested: replace an expert's photo, and choose
// which of two experts' inspections counts.

const todayInIndia = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
const answersOf = async (id: string) => {
  const insps = await json(await (await apiAs("ops")).get(`bookings/${id}/inspections`));
  return (insps.results ?? insps) as { id: string; status: string; expert: number; answers: { inspection: Record<string, unknown> } }[];
};

test("Ops replace an expert's photo: the new one counts, the old one is kept in the history", async ({ page }) => {
  const id = await submittedJob({ bookingId: "OPS-R1", door: "dent", photo: true });
  await waitForReport(id);
  const before = (await answersOf(id)).find((i) => i.status === "submitted")!.answers.inspection.door_photo as string[];
  expect(before).toHaveLength(1);

  await signIn(page, "ops");
  await page.goto(`/booking/${id}`);
  await page.getByRole("tab", { name: /Media/ }).click();
  await page.getByTestId("gallery-item").and(page.getByRole("button", { name: /^Door photo/ })).click();
  await page.getByLabel("Replace this photo").setInputFiles({ name: "new-door.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await expect(page.getByRole("status").filter({ hasText: "Replaced" })).toBeVisible({ timeout: 20_000 });

  await expect.poll(async () => (await answersOf(id)).find((i) => i.status === "submitted")!.answers.inspection.door_photo, { timeout: 15_000 })
    .not.toEqual(before);
  const after = (await answersOf(id)).find((i) => i.status === "submitted")!.answers.inspection.door_photo as string[];
  expect(after).toHaveLength(1);                              // replaced, not added
  const media = await json(await (await apiAs("ops")).get(`media/${after[0]}`));
  expect(media.status).toBe("verified");
  const old = await (await apiAs("admin")).get(`media/${before[0]}`);    // the replaced file is kept for the Admin
  expect(old.ok()).toBe(true);
});

test("two experts submitted: Ops choose which inspection counts and the conflict is gone", async ({ page }) => {
  const ops = await apiAs("ops");
  const ravi = await apiAs("expert");
  const meera = await apiAs("expert2");
  const users = await json(await (await apiAs("admin")).get("users", { params: { role: "expert" } }));
  const idOf = (name: string) => (users.results ?? users).find((u: { username: string }) => u.username === name).id as number;
  const b = await json(await ops.post("bookings", { data: { answers: {
    booking_id: "OPS-C1", customer_name: "Two Experts", customer_phone: "9876500098", address: "1 Test Street", city: "delhi",
    inspection_date: todayInIndia(), inspection_time: "09:30", inspection_type: "pdi", car_make_model: "maruti_victoris" } } }));
  const start = async (who: typeof ravi) => {
    const selfie = await uploadFile(who, b.id, "selfie", "photo", "image/jpeg", JPEG);
    await json(await who.post(`bookings/${b.id}/start`, { data: { client_uuid: crypto.randomUUID(), inspection_type: "pdi", start_answers: { selfie: [selfie] } } }));
    return selfie;
  };
  const submit = (who: typeof ravi, selfie: string, odometer: number) => who.post(`bookings/${b.id}/submit`, { data: { client_submission_uuid: crypto.randomUUID(),
    answers: { inspection: { chassis_no: "MA3YPKCSKTJ273129", door: "ok", odometer }, start: { selfie: [selfie] }, end: { taking_payment: false } } } });

  // Ravi starts and goes offline; Ops force-release and give the job to Meera, who finishes it;
  // then Ravi's offline work arrives
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: idOf("expert") } }));
  const raviSelfie = await start(ravi);
  await json(await ops.post(`bookings/${b.id}/force-release`, { data: {} }));
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: idOf("expert2") } }));
  await json(await submit(meera, await start(meera), 45));
  await json(await submit(ravi, raviSelfie, 99999));
  expect((await json(await ops.get(`bookings/${b.id}`))).conflict).toBe("TWO_EXPERTS");

  await signIn(page, "ops");
  await page.goto(`/booking/${b.id}`);
  const banner = page.getByRole("alert").filter({ hasText: "Two experts submitted this booking" });
  await expect(banner).toBeVisible();
  await expect(page.getByText("Conflict: two experts")).toBeVisible();
  const keep = banner.getByLabel("Inspection to keep");
  const ravisOption = keep.locator("option", { hasText: "Ravi Expert" });
  await keep.selectOption(await ravisOption.getAttribute("value") ?? "");
  await banner.getByRole("button", { name: "Keep this one" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Resolved" })).toBeVisible();
  await expect(banner).toBeHidden();

  const after = await json(await ops.get(`bookings/${b.id}`));
  expect(after.conflict).toBe("");
  const insps = await answersOf(b.id);
  const kept = insps.find((i) => i.status === "submitted")!;
  expect(kept.expert).toBe(idOf("expert"));
  expect(kept.answers.inspection.odometer).toBe(99999);
  expect(insps.find((i) => i.expert === idOf("expert2"))!.status).toBe("superseded");   // set aside, not deleted
});
