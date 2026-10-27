import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { formatDecimal } from "../src/lib/format";
import {
  DataProvenanceBadge,
  JobProgress,
  Money,
  VersionIdentity,
  WarningsPanel,
} from "../src/components/evidence";
import type { components } from "../src/api/generated/schema";
import fixtures from "./transport-fixtures.json";
afterEach(cleanup);
describe("exact presentation", () => {
  it.each([
    [null, "money", "Unavailable"],
    ["9007199254740993.01", "money", "$9,007,199,254,740,993.01"],
    ["-12.345", "money", "-$12.35"],
    ["0", "money", "$0.00"],
    ["9007199254740993.123456", "quantity", "9,007,199,254,740,993.123456"],
    ["-0.000001", "quantity", "-0.000001"],
    ["0.20", "percent", "20%"],
    ["-0.125", "percent", "-12.5%"],
    ["NaN", "money", "Unavailable"],
    ["1e30", "money", "Unavailable"],
    ["", "money", "Unavailable"],
  ] as const)("formats %s as %s", (value, kind, expected) =>
    expect(formatDecimal(value, kind)).toBe(expected),
  );
  it("respects locale without losing decimal cents", () =>
    expect(formatDecimal("9007199254740993.01", "money", "de-DE")).toBe(
      "9.007.199.254.740.993,01 $",
    ));
  it("renders unavailable money and version identity", () => {
    render(
      <>
        <Money value={null} />
        <VersionIdentity label="Version" identity="version-example" />
      </>,
    );
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.getByText("version-example")).toBeTruthy();
  });
});
describe("source and job states", () => {
  it.each([
    ["synthetic_fixture", "fixture", "Synthetic demo", "not live market data"],
    ["research_market_data", "stale", "Market research data", "Stale"],
    [null, "unavailable", "Source unavailable", "Freshness unavailable"],
  ] as const)("distinguishes %s", (mode, freshness, label, detail) => {
    render(
      <DataProvenanceBadge mode={mode} asOf={null} freshness={freshness} />,
    );
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.getByText(new RegExp(detail))).toBeTruthy();
  });
  it("keeps blocking warnings textual and nondismissible", () => {
    render(
      <WarningsPanel
        severity="error"
        warnings={["Stale data blocks this operation."]}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain("Stale data");
    expect(screen.queryByRole("button")).toBeNull();
  });
  it.each([
    "queued",
    "running",
    "cancel_requested",
    "completed",
    "failed",
    "cancelled",
  ] as const)("renders %s without claiming partial completion", (status) => {
    const job = { ...fixtures.job, status } as components["schemas"]["JobV1"];
    render(<JobProgress job={job} />);
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.queryByText("A sealed result is available.") !== null).toBe(
      status === "completed",
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});
