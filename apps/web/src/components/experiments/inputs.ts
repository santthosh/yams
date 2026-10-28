import type { components } from "../../api/generated/schema";

type S = components["schemas"];
export const MAX_SEED = 18446744073709551615n;
export function validSeed(value: string): boolean {
  return /^(0|[1-9][0-9]{0,19})$/.test(value) && BigInt(value) <= MAX_SEED;
}
export function positiveMoney(value: string): boolean {
  return (
    /^(0|[1-9][0-9]{0,21})(\.[0-9]{1,2})?$/.test(value) &&
    BigInt(value.replace(".", "")) > 0n
  );
}
export function coveredWindow(
  snapshot: S["SnapshotV1"] | null,
  start: string,
  end: string,
): boolean {
  const first = snapshot?.coverage.first_session;
  const last = snapshot?.coverage.last_session;
  return Boolean(
    first &&
    last &&
    /^\d{4}-\d{2}-\d{2}$/.test(start) &&
    /^\d{4}-\d{2}-\d{2}$/.test(end) &&
    start < end &&
    start >= first &&
    end <= last,
  );
}
export function serializeExperiment(
  inputs: S["ExperimentRequest"],
  seed: string,
): string {
  if (!validSeed(seed)) throw new Error("Invalid seed");
  // Numeric JSON literal, serialized from validated decimal text rather than a
  // lossy JS number. The rest of the request remains generated-client typed.
  return JSON.stringify({ ...inputs, random_seed: 0 }).replace(
    '"random_seed":0',
    `"random_seed":${seed}`,
  );
}
export function storedSeed(run: S["ExperimentDetailV1"]): string {
  return (
    /"random_seed":([0-9]+)/.exec(run.inputs_canonical_json)?.[1] ??
    "Unavailable"
  );
}
export function experimentError(code?: S["ErrorDetail"]["code"]): string {
  if (code === "VALIDATION_ERROR" || code === "WORKLOAD_LIMIT")
    return "These inputs cannot run on the pinned calendar, source or workload limits. Check the dates and snapshot coverage.";
  if (code === "NOT_FOUND")
    return "The selected version, snapshot or experiment is unavailable. Reload your choices.";
  if (code === "STATE_CONFLICT")
    return "The job changed state. Refresh its status before trying again.";
  return "Experiment storage or data integrity is unavailable. Retry when the local services are ready.";
}
