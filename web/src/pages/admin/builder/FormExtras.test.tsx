import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { FormVersion } from "../../../api/types";
import { Ratings } from "./FormExtras";

const sections = [
  { key: "exterior", title: "Exterior" },
  { key: "engine", title: "Engine bay" },
];
const version = (cats: { key: string; label: string; sections: string[] }[]) =>
  ({ rating_config: { categories: cats } }) as unknown as FormVersion;

describe("rating categories count sections by key (F-045)", () => {
  it("a saved config (keys) shows its sections picked, by title", () => {
    render(<Ratings version={version([{ key: "body", label: "Body", sections: ["exterior"] }])} sections={sections} edit run={vi.fn()} />);
    expect(screen.getByRole("button", { name: "✓ Exterior" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Engine bay" })).toHaveAttribute("aria-pressed", "false");
  });
  it("picking adds the key, and an old title-based pick can be removed", async () => {
    render(
      <Ratings
        version={version([{ key: "body", label: "Body", sections: ["Engine bay"] }])}
        sections={sections}
        edit
        run={(fn) => void fn()}
      />,
    );
    const u = userEvent.setup();
    const engine = screen.getByRole("button", { name: "✓ Engine bay" }); // saved before keys
    await u.click(engine);
    expect(screen.getByRole("button", { name: "Engine bay" })).toHaveAttribute("aria-pressed", "false");
    await u.click(screen.getByRole("button", { name: "Exterior" }));
    expect(screen.getByText("1 section")).toBeInTheDocument();
    const sent: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_u, init) => {
      sent.push(JSON.parse(String(init?.body)));
      return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
    });
    await u.click(screen.getByRole("button", { name: /^Save rat/ }));
    expect((sent[0] as { config: { categories: { sections: string[] }[] } }).config.categories[0]!.sections).toEqual(["exterior"]);
  });
});
