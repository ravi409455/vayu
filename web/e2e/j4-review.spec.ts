import { expect, test } from "@playwright/test";
import { apiAs, json, signIn, submittedJob, waitForReport } from "./api";

// J4: edit an answer -> ratings recalculate (an override is kept) -> regenerate -> download; stale save -> 409 dialog
test("J4: Ops review a completed inspection", async ({ page }) => {
  const id = await submittedJob({ bookingId: "J4-1", door: "dent", photo: true, odometer: 100 });
  const first = await waitForReport(id);
  expect(first.revision).toBe(1);
  await signIn(page, "ops");
  await page.goto(`/booking/${id}`);

  // override the Exterior rating, then edit an answer: the override stays
  await page.getByRole("tab", { name: "Ratings" }).click();
  await expect(page.getByText("Suggested").first()).toBeVisible();
  await page.getByLabel("Exterior rating").selectOption("2");
  await expect(page.getByText("Overridden").first()).toBeVisible();
  await page.getByRole("tab", { name: "Inspection" }).click();
  await page.getByLabel("Odometer").fill("150");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status").filter({ hasText: "recalculated" })).toBeVisible();
  await page.getByRole("tab", { name: "Ratings" }).click();
  await expect(page.getByLabel("Exterior rating")).toHaveValue("2");

  // the PDF is out of date until regenerated
  await page.getByRole("tab", { name: "Report" }).click();
  await expect(page.getByText(/Out of date/)).toBeVisible();
  await page.getByRole("button", { name: "Regenerate PDF" }).click();
  await expect.poll(async () => (await json(await (await apiAs("ops")).get(`bookings/${id}/report`))).revision, { timeout: 30_000 }).toBe(2);
  await page.getByRole("tab", { name: "Inspection" }).click();
  await page.getByRole("tab", { name: "Report" }).click();
  await expect(page.getByRole("link", { name: /Download J4-1PDI\.pdf/ })).toBeVisible();
  await expect(page.getByText(/Out of date/)).toHaveCount(0);
  const pdf = await page.request.get((await waitForReport(id)).url);
  expect((await pdf.body()).subarray(0, 4).toString()).toBe("%PDF");
});

test("J4b: someone else saved first: the dialog names them and retries only my change", async ({ page }) => {
  const id = await submittedJob({ bookingId: "J4-2", odometer: 10 });
  await signIn(page, "ops");
  await page.goto(`/booking/${id}`);
  await page.getByRole("tab", { name: "Inspection" }).click();
  await expect(page.getByLabel("Odometer")).toHaveValue("10");
  // an Admin edits a different field meanwhile
  const admin = await apiAs("admin");
  const insps = await json(await admin.get(`bookings/${id}/inspections`));
  const insp = (insps.results ?? insps)[0];
  await json(await admin.patch(`inspections/${insp.id}`, { data: { row_version: insp.row_version, answers: { inspection: { remarks: "Admin wrote this" } } } }));
  await page.getByLabel("Odometer").fill("99");
  await page.getByRole("button", { name: "Save changes" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("admin changed this");
  await expect(dialog).toContainText("remarks");
  await dialog.getByRole("button", { name: /Save only my 1 change/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  const after = await json(await admin.get(`bookings/${id}/inspections`));
  const answers = (after.results ?? after)[0].answers.inspection;
  expect(answers.odometer).toBe(99);                         // mine was applied
  expect(answers.remarks).toBe("Admin wrote this");         // theirs was not overwritten
});
