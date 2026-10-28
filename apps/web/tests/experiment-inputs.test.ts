import { describe, expect, it } from "vitest";
import sample from "./experiment-transport.json";
import type { components } from "../src/api/generated/schema";
import {
  coveredWindow,
  positiveMoney,
  serializeExperiment,
  storedSeed,
  validSeed,
} from "../src/components/experiments/inputs";
import candidates from "./candidate-transport.json";

type S = components["schemas"];
describe("experiment input transport", () => {
  it("preserves the full uint64 seed and exact money as JSON text", () => {
    const body = serializeExperiment(
      sample.completed.inputs as S["ExperimentRequest"],
      "18446744073709551615",
    );
    expect(body).toContain('"random_seed":18446744073709551615');
    expect(body).toContain('"initial_capital_usd":"1000.00"');
    expect(body).not.toContain('"random_seed":"');
    for (const seed of [
      "-1",
      "1.1",
      "18446744073709551616",
      "01",
      '0,"unsafe":true',
      "Infinity",
    ]) {
      expect(validSeed(seed)).toBe(false);
      expect(() =>
        serializeExperiment(
          sample.completed.inputs as S["ExperimentRequest"],
          seed,
        ),
      ).toThrow();
    }
    expect(validSeed("0")).toBe(true);
    const run = {
      ...sample.completed,
      inputs_canonical_json: body,
    } as S["ExperimentDetailV1"];
    expect(storedSeed(run)).toBe("18446744073709551615");
  });
  it("keeps USD validation independent of binary floating point", () => {
    for (const value of ["1", "0.01", "1000.00", "9999999999999999999999.99"])
      expect(positiveMoney(value)).toBe(true);
    for (const value of [
      "0",
      "0.00",
      "-1",
      "1e3",
      "01",
      "0.001",
      "1.00 USD",
      "",
    ])
      expect(positiveMoney(value)).toBe(false);
  });
  it("requires a positive contained half-open window and usable coverage", () => {
    const snapshot = candidates.snapshot as S["SnapshotV1"];
    expect(coveredWindow(snapshot, "2028-07-18", "2028-07-24")).toBe(true);
    expect(coveredWindow(snapshot, "2028-07-18", "2028-07-18")).toBe(false);
    expect(coveredWindow(snapshot, "2020-01-01", "2028-07-24")).toBe(false);
    expect(coveredWindow(snapshot, "2028-07-18", "2031-01-02")).toBe(false);
    expect(coveredWindow(snapshot, "2028-07-18", "2031-01-01")).toBe(false);
    expect(coveredWindow(snapshot, "2028-07-18", "2030-12-31")).toBe(true);
    expect(coveredWindow(null, "2028-07-18", "2028-07-24")).toBe(false);
  });
});
