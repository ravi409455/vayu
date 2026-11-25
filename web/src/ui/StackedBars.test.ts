import { describe, expect, it } from "vitest";

describe("stacked bars", () => {
  it("uses clean ticks and folds a ninth series into Other", async () => {
    const { niceTicks, foldSeries } = await import("./StackedBars");
    expect(niceTicks(4)).toEqual([0, 1, 2, 3, 4]);
    expect(niceTicks(23)).toEqual([0, 10, 20, 30]);
    expect(niceTicks(0)).toEqual([0, 1]);
    const series = Array.from({ length: 10 }, (_, i) => ({ key: `s${i}`, name: `S${i}` }));
    const cols = [{ key: "d", label: "d", long: "d", values: Object.fromEntries(series.map((s, i) => [s.key, i + 1])) }];
    const f = foldSeries(series, cols);
    expect(f.series).toHaveLength(8);
    expect(f.series[7]!.name).toBe("Other");
    expect(f.cols[0]!.values.__other).toBe(1 + 2 + 3); // the three smallest
  });
});
