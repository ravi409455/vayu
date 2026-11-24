import { expect, test } from "@playwright/test";
import { apiAs, expertId, json, signIn } from "./api";

// J2: create a booking -> assign -> reschedule -> cancel; a duplicate Booking ID is refused
test("J2: Ops run a booking from creation to cancellation", async ({ page }) => {
  await signIn(page, "ops");
  await expect(page).toHaveURL(/\/today$/);                                    // Ops land on Today
  await page.getByRole("link", { name: "Bookings", exact: true }).click();
  await page.getByRole("button", { name: "New booking" }).click();
  await page.getByLabel("Booking ID").fill("J2-100");
  await page.getByLabel("Customer name").fill("Sunita Rao");
  await page.getByLabel("Customer phone").fill("9876500123");
  await page.getByLabel("Address").fill("22 Park Street");
  await page.getByLabel("City").selectOption("delhi");
  await page.getByLabel("Date").fill("2026-12-01");
  await page.getByLabel("Time").fill("10:30");
  await page.getByLabel("Inspection type").selectOption("pdi");
  await page.getByLabel("Car make/model").selectOption("maruti_victoris");
  await page.getByRole("button", { name: "Create booking" }).click();
  await expect(page.getByRole("heading", { name: /Sunita Rao/ })).toBeVisible();
  await expect(page.getByText(/J2-100/).first()).toBeVisible();
  await expect(page.getByText("Unassigned").first()).toBeVisible();

  // assign
  await page.getByRole("button", { name: "Assign", exact: true }).click();
  await page.getByRole("dialog").getByLabel("Expert").selectOption({ label: "Ravi Expert" });
  await page.getByRole("dialog").getByRole("button", { name: "Assign an expert" }).click();
  await expect(page.getByText("Expert: Ravi Expert")).toBeVisible();
  await expect(page.getByText("Assigned").first()).toBeVisible();

  // reschedule
  await page.getByRole("button", { name: "Reschedule" }).click();
  await page.getByLabel("New date").fill("2026-12-02");
  await page.getByLabel("New time").fill("14:00");
  await page.getByRole("dialog").getByLabel("Reason").selectOption({ index: 1 });
  await page.getByRole("dialog").getByRole("button", { name: "Reschedule" }).click();
  await expect(page.getByRole("region", { name: "Activity" })).toContainText(/Rescheduled to Wed 2 Dec(ember)?( 2026)?, 2:00 pm/);

  // a duplicate Booking ID is refused, in any letter case
  await page.goto("/booking/new");
  await page.getByLabel("Booking ID").fill("j2-100");
  await page.getByLabel("Customer name").fill("Other");
  await page.getByLabel("Customer phone").fill("9876500124");
  await page.getByLabel("Address").fill("1 Road");
  await page.getByLabel("City").selectOption("pune");
  await page.getByLabel("Date").fill("2026-12-03");
  await page.getByLabel("Time").fill("09:00");
  await page.getByLabel("Inspection type").selectOption("pdi");
  await page.getByLabel("Car make/model").selectOption("tata_nexon");
  await page.getByRole("button", { name: "Create booking" }).click();
  await expect(page.getByRole("alert").first()).toContainText("already used");

  // cancel
  await page.goto("/bookings?view=all");
  await page.getByRole("link", { name: "J2-100" }).click();
  await page.getByRole("button", { name: "More actions" }).click();             // risky actions sit in the ··· menu
  await page.getByRole("menuitem", { name: "Cancel booking" }).click();
  await page.getByRole("dialog").getByLabel("Reason").selectOption({ index: 1 });
  await page.getByRole("dialog").getByRole("button", { name: "Cancel this booking" }).click();
  await expect(page.getByText("Cancelled").first()).toBeVisible();
  const ops = await apiAs("ops");
  const list = await json(await ops.get("bookings?search=J2-100"));
  expect(list.results[0].stage).toBe("cancelled");
});

test("booking filters are remembered per person", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/bookings?view=all");
  await page.getByLabel("City").selectOption("pune");
  await page.getByLabel("Stage").selectOption("cancelled");
  await page.reload();
  await expect(page.getByLabel("City")).toHaveValue("pune");
  await expect(page.getByLabel("Stage")).toHaveValue("cancelled");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("City")).toHaveValue("");
});

test("the Bookings page finds a booking by customer, and an expert cannot open the board", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/bookings");
  await page.getByLabel("Filter bookings").fill("Sunita");
  await expect(page.getByRole("link", { name: "J2-100" })).toBeVisible();
  await page.goto("/search");                                                  // the old Search page is gone
  await expect(page).toHaveURL(/\/today$/);
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await signIn(page, "expert");
  await page.goto("/bookings");
  await expect(page).toHaveURL(/\/jobs$/);
});

test("the menu and pages: Ops see only their four, nothing of the admin side", async ({ page }) => {
  await signIn(page, "ops");
  for (const name of ["Today", "Bookings", "Needs you", "Dashboard"]) await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  for (const name of ["Library", "Master lists", "Users", "Forms", "PDF templates", "Promote", "Integrations", "API keys", "Search"]) await expect(page.getByRole("link", { name })).toHaveCount(0);
  for (const path of ["/library", "/lists", "/users", "/forms", "/pdf", "/promote", "/integrations"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/today$/);
  }
});

test("delete rules: Ops may delete only a draft, Admin any booking", async ({ page }) => {
  const ops = await apiAs("ops");
  const admin = await apiAs("admin");
  const mk = async (id: string) => json(await ops.post("bookings", { data: { answers: {
    booking_id: id, customer_name: "Del Test", customer_phone: "9876500777", address: "3 Road", city: "delhi",
    inspection_date: "2026-12-05", inspection_time: "09:00", inspection_type: "pdi", car_make_model: "maruti_victoris" } } }));
  const draft = await mk("J2-DEL-A");
  const assigned = await mk("J2-DEL-B");
  await json(await ops.post(`bookings/${assigned.id}/assign`, { data: { expert: await expertId() } }));

  await signIn(page, "ops");
  await page.goto("/bookings");
  await page.getByLabel("Filter bookings").fill("J2-DEL");
  await expect(page.getByRole("link", { name: "J2-DEL-B" })).toBeVisible();
  await page.getByRole("button", { name: "Actions for J2-DEL-B" }).click();
  await expect(page.getByRole("menuitem", { name: "Delete…" })).toHaveCount(0);                // assigned: cancel only
  await page.keyboard.press("Escape");
  expect((await ops.delete(`bookings/${assigned.id}`)).status()).toBe(403);
  await page.getByRole("button", { name: "Actions for J2-DEL-A" }).click();
  await page.getByRole("menuitem", { name: "Delete…" }).click();                               // untouched draft: allowed
  await page.getByRole("dialog").getByRole("button", { name: "Delete booking" }).click();
  await expect(page.getByText("Booking deleted.")).toBeVisible();
  expect((await admin.get(`bookings/${draft.id}`)).status()).toBe(404);

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await signIn(page, "admin");
  await page.goto("/bookings");
  await page.getByLabel("Filter bookings").fill("J2-DEL-B");
  await page.getByRole("button", { name: "Actions for J2-DEL-B" }).click();
  await page.getByRole("menuitem", { name: "Delete…" }).click();                               // Admin can delete any
  await page.getByRole("dialog").getByRole("button", { name: "Delete booking" }).click();
  await expect(page.getByText("Booking deleted.")).toBeVisible();
  expect((await admin.get(`bookings/${assigned.id}`)).status()).toBe(404);
});

test("every number on Today is the count of the list it opens, even with filters saved on the Bookings page", async ({ page }) => {
  const ops = await apiAs("ops");
  const day = new Date().toISOString().slice(0, 10);
  const make = async (id: string, date: string, city: string) => json(await ops.post("bookings", { data: { answers: {
    booking_id: id, customer_name: "Count Check", customer_phone: "9876500055", address: "1 Count St", city, inspection_date: date,
    inspection_time: "10:00", inspection_type: "pdi", car_make_model: "maruti_victoris" } } }));
  await make(`CNT-${Date.now()}-a`, day, "delhi");            // unassigned today
  await make(`CNT-${Date.now()}-b`, "2026-12-20", "pune");    // unassigned, another day
  await signIn(page, "ops");
  await page.goto("/bookings?view=all");
  await page.getByLabel("City").selectOption("pune");         // a filter left behind on the Bookings page
  await page.goto("/today");
  for (const name of ["Today's bookings", "Unassigned", "In progress", "Uploading", "Completed"]) {
    await page.goto("/today");
    const card = page.getByRole("link", { name: new RegExp(`^${name}`) });
    await expect(card.locator(".kpi-value")).not.toHaveText("—");          // wait for the number to arrive
    const shown = (await card.locator(".kpi-value").innerText()).trim();
    await card.click();
    await expect(page.locator("h1 .count")).toHaveText(shown);
  }
});
