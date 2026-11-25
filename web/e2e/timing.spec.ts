import { expect, test } from "@playwright/test";
import { apiAs, json, signIn, submittedJob } from "./api";

// A job started and submitted at once took 0 minutes: under the PDI minimum (30), so "Too quick".
test("too-quick jobs show for Ops, and Admin's new limit re-flags them at once", async ({ page }) => {
  const id = await submittedJob({ bookingId: "E2E-TQ1" });
  const admin = await apiAs("admin");
  const quick = async () => (await json(await admin.get("bookings?timing=quick"))).results.map((b: { booking_id: string }) => b.booking_id);
  expect(await quick()).toContain("E2E-TQ1");

  await signIn(page, "ops");
  await page.goto("/bookings?view=quick&all=1");
  await expect(page.getByRole("row", { name: /E2E-TQ1/ })).toContainText("Too quick 0 min");
  await page.goto(`/booking/${id}`);
  await expect(page.getByRole("status", { name: "Too quick" })).toContainText("Took 0 min (min 30)");
  await expect(page.getByRole("status", { name: "Started late" })).toHaveCount(0); // booked tomorrow: not late
  await page.getByRole("status", { name: "Too quick" }).getByRole("button", { name: "Mark reviewed" }).click();
  await expect(page.getByRole("status", { name: "Too quick" })).toContainText("Reviewed by Priya Ops");
  expect(
    (await json(await admin.get("bookings?timing=quick&reviewed=0"))).results.map((b: { booking_id: string }) => b.booking_id),
  ).not.toContain("E2E-TQ1");
  await page.goto("/settings");
  await expect(page.getByText("Only Admin can change these.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "admin");
  await page.goto("/settings");
  await page.getByLabel("Minimum minutes for PDI").fill("0");
  await page.locator("header").getByRole("button", { name: "Save" }).click(); // the page's Save (storage has its own)
  await expect(page.getByText("Saved.")).toBeVisible();
  expect(await quick()).not.toContain("E2E-TQ1");
  await json(
    await admin.put("settings/timing", {
      data: { late_grace_minutes: 15, min_minutes_default: 30, min_minutes_by_type: { pdi: 30, used_car: 45, ev: 40 } },
    }),
  );
});
