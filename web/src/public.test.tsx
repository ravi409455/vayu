import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { safeDownload, validToken, VerifyPage, ZipPage } from "./pages/Public";

const res = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const at = (path: string, el: JSX.Element, route: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={el} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("customer links stay on their own endpoints (F-063)", () => {
  it("a crafted token never reaches another API path", () => {
    const f = vi.spyOn(globalThis, "fetch");
    at("/zip/..%2Fauth%2Fme", <ZipPage />, "/zip/:token");
    expect(f).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("invalid");
    expect(validToken("R5UE8w_q2tpG5p6LQtOeTPxkM6xYG1z8")).toBe(true);
    expect(validToken("6f1c2b0e-8d6a-4c4e-9a59-0c3f1e1d2a3b:1t2u3v:AbC-dEf_123")).toBe(true);
  });
  it("only an https (or, on an http test server, http) download is followed", () => {
    const here = { href: "https://app.carcid.in/zip/x", protocol: "https:" } as Location;
    expect(safeDownload("javascript:alert(1)", here)).toBeNull();
    expect(safeDownload("http://evil.example/x.zip", here)).toBeNull();
    expect(safeDownload("https://r2.example/x.zip?sig=1", here)).toBe("https://r2.example/x.zip?sig=1");
  });
});

describe("the buyer is never told a genuine report is missing because of a hiccup (H-18 web part)", () => {
  it("a server error says 'could not check right now', a 404 says 'could not find'", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(res(500, {}));
    at("/verify/R5UE8w_q2tpG5p6LQtOeTPxkM6xYG1z8", <VerifyPage />, "/verify/:token");
    expect(await screen.findByText("We could not check this report right now.")).toBeInTheDocument();
    expect(screen.queryByText(/could not find/)).toBeNull();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});

describe("ZIP page (F-176)", () => {
  it("keeps polling through 429, slower each time, and stops on 404", async () => {
    vi.useFakeTimers();
    const f = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(res(200, { status: "building", progress: 10 }))
      .mockResolvedValueOnce(res(429, { detail: "slow down" }))
      .mockResolvedValueOnce(res(404, {}));
    at("/zip/abcdefgh12345", <ZipPage />, "/zip/:token");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("Preparing… 10%")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    }); // next try waits longer than before
    expect(f).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(f).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/Still working on it/)).toBeInTheDocument(); // 429: not "not available"
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(f).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("alert")).toHaveTextContent("invalid, expired");
  });
});
