import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import { apiAs, expertId, JPEG, json, signIn, uploadFile } from "./api";

test.use({ permissions: ["geolocation"], geolocation: { latitude: 28.6139, longitude: 77.209 } });

async function assignedJob(bookingId: string): Promise<string> {
  const ops = await apiAs("ops");
  const b = await json(
    await ops.post("bookings", {
      data: {
        answers: {
          booking_id: bookingId,
          customer_name: "Upload Test",
          customer_phone: "9876500012",
          address: "8 Lake View Rd",
          city: "delhi",
          inspection_date: "2026-11-25",
          inspection_time: "11:30",
          inspection_type: "pdi",
          car_make_model: "maruti_victoris",
        },
      },
    }),
  );
  await json(await ops.post(`bookings/${b.id}/assign`, { data: { expert: await expertId() } }));
  return b.id as string;
}

// H-16: the phone (or another tab) is still sending a file; opening the lead on the web must not delete it.
test("opening a lead on the web keeps another device's unfinished upload", async ({ page }) => {
  const id = await assignedJob("UP-1");
  const phone = await apiAs("expert");
  const selfie = await uploadFile(phone, id, "selfie", "photo", "image/jpeg", JPEG);
  await json(
    await phone.post(`bookings/${id}/start`, {
      data: { client_uuid: crypto.randomUUID(), inspection_type: "pdi", start_answers: { selfie: [selfie] } },
    }),
  );
  const init = await json(
    await phone.post("media/initiate", {
      data: {
        booking: id,
        client_uuid: crypto.randomUUID(),
        field_key: "door_photo",
        kind: "photo",
        content_type: "image/jpeg",
        size: JPEG.length,
        sha256: "0".repeat(64),
        source: "camera",
      },
    }),
  );
  expect(init.status).toBe("pending");

  await signIn(page, "expert");
  const listed = page.waitForResponse((r) => r.url().endsWith(`bookings/${id}/media`));
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Continue inspection" }).click();
  await expect(page.getByText(/Step 1 of/)).toBeVisible();
  expect((await (await listed).json()).map((m: { id: string }) => m.id)).toContain(init.id);
  await page.waitForTimeout(1500); // what the wizard does with the server's files when it opens
  expect((await phone.get(`media/${init.id}`)).status()).toBe(200);
});

// H-15: the expert submitted while a photo was still sending, then reloaded: the lead page carries on with it.
test("a submitted lead sends the file the browser kept, after a reload", async ({ page }) => {
  const id = await assignedJob("UP-2");
  const phone = await apiAs("expert");
  const selfie = await uploadFile(phone, id, "selfie", "photo", "image/jpeg", JPEG);
  await json(
    await phone.post(`bookings/${id}/start`, {
      data: { client_uuid: crypto.randomUUID(), inspection_type: "pdi", start_answers: { selfie: [selfie] } },
    }),
  );
  const clientUuid = crypto.randomUUID();
  const init = await json(
    await phone.post("media/initiate", {
      data: {
        booking: id,
        client_uuid: clientUuid,
        field_key: "door_photo",
        kind: "photo",
        content_type: "image/jpeg",
        size: JPEG.length,
        sha256: createHash("sha256").update(JPEG).digest("hex"),
        source: "camera",
      },
    }),
  );
  await json(
    await phone.post(`bookings/${id}/submit`, {
      data: {
        client_submission_uuid: crypto.randomUUID(),
        answers: {
          inspection: { chassis_no: "MA3YPKCSKTJ273129", door: "dent", door_photo: [init.id], odometer: 100 },
          start: { selfie: [selfie] },
          end: { taking_payment: false },
        },
      },
    }),
  );

  await signIn(page, "expert");
  await page.evaluate(
    async ({ job, bytes }) => {
      // what the browser kept before the reload
      const db = await new Promise<IDBDatabase>((res, rej) => {
        const r = indexedDB.open("vayu-uploads", 1);
        r.onupgradeneeded = () => r.result.createObjectStore("jobs", { keyPath: "clientUuid" });
        r.onsuccess = () => res(r.result);
        r.onerror = () => rej(r.error);
      });
      await new Promise((res, rej) => {
        const t = db.transaction("jobs", "readwrite");
        t.objectStore("jobs").put({ ...job, blob: new Blob([new Uint8Array(bytes)], { type: "image/jpeg" }) });
        t.oncomplete = res;
        t.onerror = rej;
      });
    },
    {
      job: {
        clientUuid,
        bookingId: id,
        fieldKey: "door_photo",
        kind: "photo",
        contentType: "image/jpeg",
        name: "door.jpg",
        sha256: createHash("sha256").update(JPEG).digest("hex"),
        assetId: init.id,
        source: "camera",
      },
      bytes: [...JPEG],
    },
  );
  await page.goto(`/jobs/${id}`);
  await expect(page.getByText("Completed. Everything arrived")).toBeVisible({ timeout: 30_000 });
});

const photo = (name: string) => ({ name, mimeType: "image/jpeg", buffer: JPEG });

// F-143: no connection when the photo is picked: it is kept and sent once the connection is back.
test("a photo picked with no connection is kept and sent later", async ({ page }) => {
  const id = await assignedJob("UP-3");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.route("**/api/v1/media/initiate", (r) => r.abort("internetdisconnected"));
  await page.getByTestId("camera-selfie").setInputFiles(photo("selfie.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await expect(page.getByText(/No connection: kept on this device/)).toBeVisible();
  await expect(page.getByText(/Check its type and size/)).toHaveCount(0);
  await page.unroute("**/api/v1/media/initiate");
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByLabel(/^Upload /)).toHaveCount(0, { timeout: 15_000 }); // sent: no progress bar left
  const draft = await page.evaluate((k) => localStorage.getItem(k), `vayu:draft:${id}`);
  expect(draft).not.toContain("local-"); // the answer now holds the server's id
});

// F-125: the same lead in two tabs: the other tab takes the new answers and says so.
test("two tabs on one lead do not silently overwrite each other", async ({ page, context }) => {
  const id = await assignedJob("UP-4");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.getByTestId("camera-selfie").setInputFiles(photo("selfie.jpg"));
  await expect(page.getByTestId("media-item")).toHaveCount(1);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel("Chassis number").fill("AAA");
  const other = await context.newPage();
  await other.goto(`/jobs/${id}`);
  await expect(other.getByLabel("Chassis number")).toHaveValue("AAA");
  await page.getByLabel("Chassis number").fill("BBB");
  await expect(other.getByText("This lead is also open in another tab.")).toBeVisible();
  await expect(other.getByLabel("Chassis number")).toHaveValue("BBB");
  await other.waitForTimeout(500);
  await expect(page.getByLabel("Chassis number")).toHaveValue("BBB");
});

// R-06 / F-242: sign-out says what is not sent yet; signing out anyway leaves nothing behind.
test("sign-out warns about unsent work, then leaves no drafts or files in the browser", async ({ page }) => {
  const id = await assignedJob("UP-5");
  await signIn(page, "expert");
  await page.goto(`/jobs/${id}`);
  await page.getByRole("button", { name: "Start inspection" }).click();
  await page.route("**/api/v1/media/initiate", (r) => r.abort("internetdisconnected")); // the photo stays on this computer
  await page.getByTestId("camera-selfie").setInputFiles(photo("selfie.jpg"));
  await expect(page.getByText(/No connection: kept on this device/)).toBeVisible();
  const jobs = () =>
    page.evaluate(
      () =>
        new Promise<number>((res) => {
          const r = indexedDB.open("vayu-uploads", 1);
          r.onsuccess = () => {
            const q = r.result.transaction("jobs").objectStore("jobs").count();
            q.onsuccess = () => res(q.result);
          };
        }),
    );
  expect(await jobs()).toBe(1);

  await page.getByRole("button", { name: /account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  const dialog = page.getByRole("dialog", { name: "Sign out with work not sent?" });
  await expect(dialog).toContainText("1 inspection draft and 1 photo or file");
  await dialog.getByRole("button", { name: "Stay signed in" }).click();
  await expect(page).toHaveURL(new RegExp(`/jobs/${id}`)); // nothing lost

  await page.getByRole("button", { name: /account menu/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Sign out and delete it" }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(
    await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("vayu:draft:") || k.startsWith("vayu:job:"))),
  ).toEqual([]);
  expect(await jobs()).toBe(0);
});
