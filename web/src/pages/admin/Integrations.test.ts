import { describe, expect, it } from "vitest";

describe("integration words", () => {
  it("names events and delivery errors in words", async () => {
    const { errorWord } = await import("./Integrations");
    const { eventWord } = await import("../../lib/integrationDef");
    expect(eventWord("booking.updated")).toBe("Booking updated");
    expect(eventWord("pdf.ready")).toBe("PDF ready");
    expect(errorWord("blocked_address")).toMatch(/not allowed/);
    expect(errorWord("http_503")).toBe("Server answered 503");
    expect(errorWord("something_new")).toBe("something_new");
  });
});
