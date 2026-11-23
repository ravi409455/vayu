import { describe, expect, it } from "vitest";
import { parseFields } from "./ApiKeys";

describe("API key field scope", () => {
  it("empty means no access, never every field", () => {
    expect(parseFields("")).toEqual([]);
    expect(parseFields("   ")).toEqual([]);
  });
  it("every field only when * is typed on its own", () => {
    expect(parseFields("*")).toEqual(["*"]);
    expect(parseFields(" * ")).toEqual(["*"]);
    expect(parseFields("city, *")).toEqual(["city"]);       // a stray * inside a list is not a wildcard
  });
  it("a list of keys", () => {
    expect(parseFields("city, address ,, odometer")).toEqual(["city", "address", "odometer"]);
  });
});
