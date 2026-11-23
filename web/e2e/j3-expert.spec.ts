import { expect, test } from "@playwright/test";
import { apiAs, json, signIn } from "./api";

// a real (tiny) JPEG
const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDzSiiivkT+iAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP//Z",
  "base64");
const file = (name: string) => ({ name, mimeType: "image/jpeg", buffer: JPEG });

test.use({ permissions: ["geolocation"], geolocation: { latitude: 28.6139, longitude: 77.209 } });

async function assignedJob(bookingId: string) {
  const ops = await apiAs("ops");
  const admin = await apiAs("admin");
  const users = await json(await admin.get("users"));
  const expert = (users.results ?? users).find((u: { username: string }) => u.username === "expert");
  const b = await json(await ops.post("bookings", { data: { answers: {
    booking_id: bookingId, customer_name: "Kavya Rao", customer_phone: "9876500011", address: "7 Lake View Rd", city: "delhi",
    inspection_date: "2026-11-24", inspection_time: "11:30", inspection_type: "pdi", car_make_model: "maruti_victoris" } } }));
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: expert.id } }));
  return b.id as string;
}

// J3: My Jobs -> confirm -> check-in -> full inspection with photos -> payment -> submit -> Completed -> PDF
test("J3: expert completes a full inspection on the web", async ({ page }) => {
  const id = await assignedJob("J3-1");
  await signIn(page, "expert");
  await expect(page).toHaveURL(/\/jobs$/);
  await page.getByRole("link", { name: "Job J3-1" }).click();
  await expect(page.getByText("7 Lake View Rd")).toBeVisible();
  await expect(page.getByRole("link", { name: /9876500011/ })).toHaveAttribute("href", "tel:+919876500011");
  await page.getByRole("button", { name: "Start inspection" }).click();

  // check-in: location + selfie
  await expect(page.getByText(/Step 1 of/)).toBeVisible();
  await expect(page.getByTestId("gps-value")).toContainText("28.6139");           // taken by itself
  await page.getByTestId("camera-selfie").setInputFiles(file("selfie.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await page.getByRole("button", { name: "Next" }).click();

  // exterior: a dent needs a photo
  await page.getByLabel("Chassis number").fill("MA3YPKCSKTJ273129");
  await page.getByRole("radio", { name: "Dent" }).click();
  await page.getByLabel("Odometer").fill("120");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Remarks").fill("Small dent on the driver door, customer informed.");
  await page.getByRole("button", { name: "Next" }).click();

  // wrap-up: pay later
  await page.getByRole("radio", { name: "Pay later" }).click();
  await page.getByRole("button", { name: "Next" }).click();

  // review: the door photo is still missing, and the review says so
  await expect(page.getByRole("alert")).toContainText("1 thing still needed");
  await expect(page.getByRole("button", { name: "Submit inspection" })).toBeDisabled();
  await page.getByRole("button", { name: "Door photo" }).click();
  await page.getByTestId("camera-door_photo").setInputFiles(file("door.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  while (!(await page.getByRole("heading", { name: "Before you submit" }).isVisible())) await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Everything required" })).toBeVisible();
  await page.getByRole("button", { name: "Submit inspection" }).click();

  // uploading finishes by itself and the booking completes
  await expect(page.getByText("Completed. Everything arrived")).toBeVisible({ timeout: 60_000 });
  const ops = await apiAs("ops");
  await expect.poll(async () => {
    const r = await ops.get(`bookings/${id}/report`);
    return r.ok() ? (await r.json()).status : `HTTP ${r.status()}`;
  }, { timeout: 40_000 }).toBe("ready");
  const report = await json(await ops.get(`bookings/${id}/report`));
  expect(report.filename).toBe("J3-1PDI.pdf");
});

test("J3b: GPS denied shows 'GPS unavailable' and does not block the job", async ({ browser }) => {
  const id = await assignedJob("J3-2");
  const ctx = await browser.newContext({ baseURL: "http://localhost:5173", permissions: [] });
  const page = await ctx.newPage();
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await expect(page.getByRole("status").filter({ hasText: "GPS unavailable" })).toBeVisible();   // asked by itself, refused
  await page.getByRole("button", { name: "Next" }).click();             // not blocked
  await expect(page.getByText(/Step 2 of/)).toBeVisible();
  await ctx.close();
});

test("J3c: a refresh keeps the draft and the pending upload carries on", async ({ page }) => {
  const id = await assignedJob("J3-3");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Odometer").fill("77");
  await page.getByRole("button", { name: "Next" }).click();
  await page.reload();
  await expect(page.getByText(/Step 3 of/)).toBeVisible();         // same step
  await page.getByRole("button", { name: "Back" }).click();
  await expect(page.getByLabel("Odometer")).toHaveValue("77");     // same answer
});

test("J3d: an upload that could not reach storage resumes by itself after a refresh", async ({ page }) => {
  const id = await assignedJob("J3-4");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.route("http://localhost:5055/**", (r) => r.abort());               // storage is unreachable
  await page.getByTestId("camera-selfie").setInputFiles(file("selfie.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await expect(page.getByText("Will retry")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/files 0\/1 sent/)).toBeVisible();
  await page.unroute("http://localhost:5055/**");                               // back online
  await page.reload();                                                          // the page forgot everything in memory
  await expect(page.getByText(/files 1\/1 sent/)).toBeVisible({ timeout: 30_000 });
});
