import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PdfProgress } from "./PdfProgress";

describe("PDF progress bar", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());
  const value = () => Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"));

  it("fills to about 90% over 7 seconds, then says it's taking longer", () => {
    render(<PdfProgress />);
    expect(value()).toBe(0);
    expect(screen.getByText("Usually about 7 seconds")).toBeTruthy();
    act(() => void vi.advanceTimersByTime(3500));
    expect(value()).toBeGreaterThanOrEqual(44);
    expect(value()).toBeLessThanOrEqual(46);
    act(() => void vi.advanceTimersByTime(4000));
    expect(screen.getByText("Taking longer than usual")).toBeTruthy();
    act(() => void vi.advanceTimersByTime(60_000));
    expect(value()).toBeLessThan(100); // never claims done before the PDF arrives
  });
});
