import { expect, test } from "@playwright/test";
import { apiAs, json, signIn } from "./api";

// J2: create a booking -> assign -> reschedule -> cancel; a duplicate Booking ID is refused
test("J2: Ops run a booking from creation to cancellation", async ({ page }) => {
  await signIn(page, "ops");
  await expect(page).toHaveURL(/\/board$/);
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
  await expect(page.getByRole("heading", { name: /J2-100/ })).toBeVisible();
  await expect(page.getByText("Not assigned").first()).toBeVisible();

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
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByText("2026-12-01 10:30 → 2026-12-02 14:00")).toBeVisible();

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
  await page.goto("/board");
  await page.getByRole("link", { name: "J2-100" }).click();
  await page.getByRole("button", { name: "Cancel booking" }).click();
  await page.getByRole("dialog").getByLabel("Reason").selectOption({ index: 1 });
  await page.getByRole("dialog").getByRole("button", { name: "Cancel this booking" }).click();
  await expect(page.getByText("Cancelled").first()).toBeVisible();
  const ops = await apiAs("ops");
  const list = await json(await ops.get("bookings?search=J2-100"));
  expect(list.results[0].stage).toBe("cancelled");
});

test("job board filters are remembered per person", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/board");
  await page.getByLabel("City").selectOption("pune");
  await page.getByLabel("Stage").selectOption("cancelled");
  await page.reload();
  await expect(page.getByLabel("City")).toHaveValue("pune");
  await expect(page.getByLabel("Stage")).toHaveValue("cancelled");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByLabel("City")).toHaveValue("");
});

test("global search finds a booking by customer, and an expert cannot open the board", async ({ page }) => {
  await signIn(page, "ops");
  await page.goto("/search");
  await page.getByLabel("Search everything").fill("Sunita");
  await expect(page.getByRole("link", { name: "J2-100" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "expert");
  await page.goto("/board");
  await expect(page).toHaveURL(/\/jobs$/);
});
