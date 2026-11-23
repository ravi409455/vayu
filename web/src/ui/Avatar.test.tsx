import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Avatar, colourFor, initials } from "./Avatar";

describe("initials", () => {
  it("uses the first and last word, one letter for one word, a mark for nothing", () => {
    expect(initials("Ravi Kumar")).toBe("RK");
    expect(initials("  meera   anand  iyer ")).toBe("MI");
    expect(initials("expert")).toBe("E");
    expect(initials("")).toBe("?");
    expect(initials("   ")).toBe("?");
  });
});
describe("colour", () => {
  it("is stable for a person and spread across people", () => {
    expect(colourFor("Ravi")).toBe(colourFor("Ravi"));
    const all = new Set(["Ravi", "Meera", "Asha", "Priya", "Nina", "Arjun", "Kavya", "Sunita"].map(colourFor));
    expect(all.size).toBeGreaterThan(2);
  });
});
describe("Avatar", () => {
  it("shows the picture when there is one", () => {
    render(<Avatar who={{ id: 1, name: "Ravi Kumar", avatar_url: "/api/v1/users/1/picture?v=2" }} />);
    expect(screen.getByAltText("Picture of Ravi Kumar")).toHaveAttribute("src", "/api/v1/users/1/picture?v=2");
  });
  it("shows initials when there is no picture, using the username if the name is empty", () => {
    const { rerender } = render(<Avatar who={{ name: "Ravi Kumar" }} />);
    expect(screen.getByRole("img", { name: "Ravi Kumar" })).toHaveTextContent("RK");
    rerender(<Avatar who={{ username: "expert2", name: "" }} />);
    expect(screen.getByRole("img", { name: "expert2" })).toHaveTextContent("E");
    rerender(<Avatar who={{ id: 4 }} />);
    expect(screen.getByRole("img", { name: "Person" })).toHaveTextContent("?");
  });
  it("falls back to initials when the picture does not load, and tries again for a new picture", () => {
    const { rerender } = render(<Avatar who={{ name: "Ravi Kumar", avatar_url: "/a?v=1" }} />);
    fireEvent.error(screen.getByAltText("Picture of Ravi Kumar"));
    expect(screen.getByRole("img", { name: "Ravi Kumar" })).toHaveTextContent("RK");
    rerender(<Avatar who={{ name: "Ravi Kumar", avatar_url: "/a?v=2" }} />);
    expect(screen.getByAltText("Picture of Ravi Kumar")).toBeInTheDocument();
  });
  it("is sized as asked", () => {
    render(<Avatar who={{ name: "A B" }} size={48} />);
    expect(screen.getByRole("img")).toHaveStyle({ width: "48px", height: "48px" });
  });
});
