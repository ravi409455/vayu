import { describe, expect, it } from "vitest";
import { phoneWords } from "./Users";

const p = (over: Partial<Parameters<typeof phoneWords>[0] & object>) => ({
  devices: 1,
  drafts: 0,
  files: 0,
  unknown: false,
  signed_out_holding: 0,
  last_seen_at: null,
  ...over,
});

describe("deactivate and sign-out warnings say what the phone holds (F-243)", () => {
  it("names what would be lost", () => {
    expect(phoneWords(p({ drafts: 1, files: 3 }))).toBe(
      "Their phone still holds 1 unfinished booking and 3 files not yet on the server. These are lost.",
    );
    expect(phoneWords(p({ files: 1 }))).toMatch(/^Their phone still holds 1 file not/);
  });
  it("says when nothing is at risk, and when it cannot know", () => {
    expect(phoneWords(p({}))).toBe("Their phone has sent everything. Nothing is lost.");
    expect(phoneWords(p({ devices: 0 }))).toMatch(/no phone signed in/);
    expect(phoneWords(p({ unknown: true }))).toMatch(/has not said what it holds/);
    expect(phoneWords(undefined)).toBe("Checking their phone…");
  });
  it("counts a phone that signed out still holding work", () => {
    expect(phoneWords(p({ devices: 0, signed_out_holding: 1, drafts: 2, files: 5 }))).toBe(
      "Their phone signed out but still holds 2 unfinished bookings and 5 files not yet on the server. These are lost.",
    );
  });
});
