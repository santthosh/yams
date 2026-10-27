import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "../app/page";

describe("foundation shell", () => {
  it("clearly labels paper scope and unavailable investment results", () => {
    render(<Home />);
    expect(screen.getByText("Paper only")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "A clear starting point.",
    );
    expect(screen.getByText(/contains no market data/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
