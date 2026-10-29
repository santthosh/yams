import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../src/components/workspace-views";
import { WorkspaceProvider } from "../src/components/workspace-provider";
import fixtures from "./transport-fixtures.json";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("foundation shell", () => {
  it("loads actual transport metadata without inventing a portfolio", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) =>
        Response.json(
          request.url.endsWith("/health")
            ? fixtures.health
            : fixtures.workspace,
        ),
      ),
    );
    render(
      <WorkspaceProvider>
        <Dashboard />
      </WorkspaceProvider>,
    );
    expect(screen.getByRole("status").textContent).toContain("Initializing");
    await waitFor(() =>
      expect(screen.getByText("Ready to explore")).toBeTruthy(),
    );
    expect(screen.getByText("SYNTHETIC_DATA_ONLY")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Open paper portfolios →" })
        .getAttribute("href"),
    ).toBe("/portfolios");
    expect(screen.queryByText("No paper portfolio yet")).toBeNull();
    expect(screen.queryByText("$0.00")).toBeNull();
    expect(
      screen.queryByRole("button", { name: /trade|buy|sell/i }),
    ).toBeNull();
  });
  it("surfaces a failed workspace read even when health succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (request: Request) =>
        request.url.endsWith("/health")
          ? Response.json(fixtures.health)
          : Response.json(
              {
                error: {
                  correlation_id: "33333333-3333-4333-8333-333333333333",
                },
              },
              { status: 503 },
            ),
      ),
    );
    render(
      <WorkspaceProvider>
        <Dashboard />
      </WorkspaceProvider>,
    );
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.queryByText("Ready to explore")).toBeNull();
    expect(
      screen.getByText("33333333-3333-4333-8333-333333333333"),
    ).toBeTruthy();
  });
  it("shows a safe error rather than raw transport exceptions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("secret_database_password");
      }),
    );
    render(
      <WorkspaceProvider>
        <Dashboard />
      </WorkspaceProvider>,
    );
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.queryByText(/secret_database_password/)).toBeNull();
  });
});
