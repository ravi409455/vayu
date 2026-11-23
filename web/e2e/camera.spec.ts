import { expect, test } from "@playwright/test";
import { apiAs, expertId, JPEG, json, signIn } from "./api";

test.use({
  permissions: ["geolocation", "camera", "microphone"], geolocation: { latitude: 28.6, longitude: 77.2 },
  launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
});

async function job(ref: string): Promise<string> {
  const ops = await apiAs("ops");
  const b = await json(await ops.post("bookings", { data: { answers: {
    booking_id: ref, customer_name: "Camera Test", customer_phone: "9876500055", address: "1 Lens Rd", city: "delhi",
    inspection_date: "2026-11-26", inspection_time: "09:00", inspection_type: "pdi", car_make_model: "maruti_victoris" } } }));
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: await expertId() } }));
  return b.id as string;
}

test("the camera opens inside the page, takes a photo, and it uploads", async ({ page }) => {
  const id = await job("CAM-1");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.getByRole("button", { name: /Open camera: photo/ }).click();
  const cam = page.getByRole("dialog");
  await expect(cam.getByLabel("Live camera")).toBeVisible();
  await expect.poll(async () => cam.getByLabel("Live camera").evaluate((v: HTMLVideoElement) => v.videoWidth)).toBeGreaterThan(0);
  await cam.getByRole("button", { name: "Take photo" }).click();
  await expect(cam.getByAltText("Preview of what you captured")).toBeVisible();
  await cam.getByRole("button", { name: "Retake" }).click();
  await cam.getByRole("button", { name: "Take photo" }).click();
  await cam.getByRole("button", { name: "Use this photo" }).click();
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await expect(page.getByText(/files 1\/1 sent/)).toBeVisible({ timeout: 30_000 });
});

test("attach still works for the same field (both options are offered)", async ({ page }) => {
  const id = await job("CAM-2");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await expect(page.getByRole("button", { name: /Attach a photo/ })).toHaveCount(0);     // the check-in selfie is camera-only
  await page.getByTestId("camera-selfie").setInputFiles({ name: "s.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("radio", { name: "Dent" }).click();                                // reveals the door photo
  await expect(page.getByRole("button", { name: /Attach a photo/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Open camera: photo/ })).toBeVisible();
});

test("a refused camera says why and offers the other ways", async ({ browser }) => {
  const id = await job("CAM-3");
  const ctx = await browser.newContext({ baseURL: "http://localhost:5173", permissions: ["geolocation"], geolocation: { latitude: 1, longitude: 1 },
    ignoreHTTPSErrors: true });
  const page = await ctx.newPage();
  await page.addInitScript(() => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException("no", "NotAllowedError")); });
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.getByRole("button", { name: /Open camera: photo/ }).click();
  await expect(page.getByRole("alert")).toContainText("permission was refused");
  await expect(page.getByRole("button", { name: "Use the device's camera app" })).toBeVisible();
  await ctx.close();
});
