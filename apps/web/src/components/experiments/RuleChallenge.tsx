"use client";
import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import { Card } from "../evidence";
import { Button } from "../ui/button";
import { validName } from "../strategy/config-form";
import {
  configDifferences,
  fairRerunBody,
  oneRuleConfig,
  type Run,
} from "./comparison";

type S = components["schemas"];
export function RuleChallenge({
  source,
  onBusy,
}: {
  source: Run;
  onBusy: (busy: boolean) => void;
}) {
  const [cap, setCap] = useState(
    source.strategy_config.portfolio.max_position_weight,
  );
  const [name, setName] = useState("");
  const [published, setPublished] = useState<S["StrategyV1"] | null>(null);
  const [accepted, setAccepted] = useState<S["ExperimentAccepted"] | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  let config = source.strategy_config;
  let invalid = "";
  try {
    config = oneRuleConfig(source.strategy_config, cap);
  } catch (reason) {
    invalid = (reason as Error).message;
  }
  const diff = invalid ? [] : configDifferences(source.strategy_config, config);
  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || invalid || !validName(name) || published || uncertain)
      return;
    lock.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const result = await createApiClient(window.location.origin).POST(
        "/api/v1/strategies",
        { body: { name, config } },
      );
      if (result.data) setPublished(result.data);
      else if ([409, 422].includes(result.response.status))
        setError(
          "The name or rule was rejected. Check the name, cap and strategy constraints; originals are unchanged.",
        );
      else {
        setUncertain(true);
        setError(
          "Publication could not be confirmed. Inspect Strategy Lab before publishing again.",
        );
      }
    } catch {
      setUncertain(true);
      setError(
        "Publication could not be confirmed. Inspect Strategy Lab before publishing again.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  async function run() {
    if (!published || lock.current || accepted || uncertain) return;
    lock.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const body = {
        ...source.inputs,
        strategy_version_id: published.published_version.id,
      };
      const response = await createApiClient(window.location.origin).POST(
        "/api/v1/experiments",
        {
          body,
          bodySerializer: () =>
            fairRerunBody(source, published.published_version.id),
        },
      );
      if (response.data) setAccepted(response.data);
      else if ([404, 422].includes(response.response.status))
        setError(
          "The challenge run was rejected. The published fork is retained; inspect its rules and source coverage before retrying.",
        );
      else {
        setUncertain(true);
        setError(
          "Run submission could not be confirmed. Inspect experiment history before submitting again. The published fork is retained.",
        );
      }
    } catch {
      setUncertain(true);
      setError(
        "Run submission could not be confirmed. Inspect experiment history before submitting again. The published fork is retained.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <Card title="Change one rule">
      <p>
        Challenge the reference strategy by changing only its maximum
        single-position weight. All other rules and experiment settings stay
        pinned to the source. Multi-rule changes belong in{" "}
        <Link href="/lab/strategies">the full Strategy Lab editor</Link>.
      </p>
      <p>
        Source experiment{" "}
        <Link href={`/lab/experiments/${source.id}`}>{source.id}</Link> ·
        version <code>{source.inputs.strategy_version_id}</code>
      </p>
      <form onSubmit={(event) => void publish(event)}>
        <fieldset
          disabled={busy || Boolean(published) || uncertain}
          className="inspection-form"
        >
          <legend>Controlled challenge</legend>
          <label>
            New maximum position weight
            <input
              name="cap"
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              type="text"
              inputMode="decimal"
              required
              aria-describedby="challenge-rule-help"
            />
          </label>
          <label>
            Challenge strategy name
            <input
              name="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              required
            />
          </label>
          <p id="challenge-rule-help">
            Use 0.10 for 10%. The backend validates the complete rules; changing
            the cap may leave more cash.
          </p>
          {invalid ? (
            <p role="status">{invalid}</p>
          ) : (
            <ul>
              {diff.map((row) => (
                <li key={row.field}>
                  <code>{row.field}</code>: {row.before} → {row.after}
                </li>
              ))}
            </ul>
          )}
          <Button type="submit" disabled={Boolean(invalid) || !validName(name)}>
            Publish challenge version
          </Button>
        </fieldset>
      </form>
      {published && (
        <div role="status">
          <p>
            Published immutable fork{" "}
            <Link href={`/lab/strategies?strategy=${published.id}`}>
              {published.name}
            </Link>{" "}
            · version <code>{published.published_version.id}</code>. The source
            and its results remain unchanged.
          </p>
          <Button
            onClick={() => void run()}
            disabled={busy || Boolean(accepted) || uncertain}
          >
            Run challenge with source settings
          </Button>
        </div>
      )}
      {error && (
        <p role="alert">
          {error}{" "}
          <Link href="/lab/experiments">Inspect experiment history</Link>
        </p>
      )}
      {accepted && (
        <p role="status">
          Challenge queued.{" "}
          <Link href={`/lab/experiments/${accepted.experiment_id}`}>
            Follow its report
          </Link>{" "}
          or{" "}
          <Link
            href={`/lab/compare?ids=${source.id},${accepted.experiment_id}`}
          >
            Open source and challenge comparison
          </Link>
          . The comparison link retains both immutable experiment identities and
          derives their rule difference from stored configurations.
        </p>
      )}
    </Card>
  );
}
