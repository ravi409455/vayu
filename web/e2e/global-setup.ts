import { writeFileSync } from "node:fs";
import { seedForms } from "./api";

// Runs once after the servers are up and the database was reset: publish the shared forms.
export default async function globalSetup(): Promise<void> {
  const ids = await seedForms();
  writeFileSync("e2e/.seed.json", JSON.stringify(ids));
}
