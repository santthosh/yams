"use client";

import { useRef, useState, type FormEvent } from "react";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import { Card } from "../evidence";
import { Button } from "../ui/button";
import {
  changes,
  configFromDraft,
  DraftError,
  familyText,
  fieldsFor,
  initialDraft,
  validName,
} from "./config-form";

type S = components["schemas"];
export function VersionEditor({
  strategy,
  version,
  onPublished,
  onBusy,
  unavailable = false,
}: {
  strategy: S["StrategyV1"];
  version: S["StrategyVersionV1"];
  onPublished: (root: S["StrategyV1"], version: S["StrategyVersionV1"]) => void;
  onBusy: (busy: boolean) => void;
  unavailable?: boolean;
}) {
  const [draft, setDraft] = useState(() => initialDraft(version.config));
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const forkSubmit = useRef<HTMLButtonElement>(null);
  const fields = fieldsFor(version.config);
  let edited = version.config;
  let invalid = "";
  try {
    edited = configFromDraft(version.config, draft);
  } catch (reason) {
    invalid =
      reason instanceof DraftError
        ? reason.message
        : "These rules cannot be prepared for publication.";
  }
  const diff = invalid ? [] : changes(version.config, edited);

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (unavailable || submitting.current || !form.current?.reportValidity())
      return;
    const fork =
      (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ===
      "fork";
    if (fork && !validName(name)) {
      setError(
        "Give the fork a name of 1–120 characters without control characters.",
      );
      nameInput.current?.focus();
      return;
    }
    let config: S["StrategyConfigV1"];
    try {
      config = configFromDraft(version.config, draft);
    } catch (reason) {
      setError(
        reason instanceof DraftError
          ? reason.message
          : "Check the rule fields before publishing.",
      );
      return;
    }
    submitting.current = true;
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const api = createApiClient(window.location.origin);
      if (fork) {
        const response = await api.POST("/api/v1/strategies", {
          body: { name, config },
        });
        if (response.data) {
          onPublished(response.data, response.data.published_version);
          return;
        }
        setError(
          response.response.status === 409
            ? "That strategy name is already in use. Inspect the saved strategy or choose another name; your edits are kept."
            : response.response.status === 422
              ? "The rules or name were rejected. Check the fields, score weights and history coverage; your edits are kept."
              : "Publication could not be confirmed. Reload strategies and inspect the fork before trying again; your edits are kept.",
        );
      } else {
        const response = await api.POST(
          "/api/v1/strategies/{strategy_id}/versions",
          { params: { path: { strategy_id: strategy.id } }, body: config },
        );
        if (response.data) {
          onPublished(
            { ...strategy, published_version: response.data },
            response.data,
          );
          return;
        }
        setError(
          response.response.status === 422
            ? "The rules were rejected. Check the fields, score weights and required history; your edits are kept."
            : response.response.status === 404
              ? "The source strategy was not found. Reload strategies before publishing."
              : "Publication could not be confirmed. Inspect or reload version history before trying again; your edits are kept.",
        );
      }
    } catch {
      setError(
        fork
          ? "Publication could not be confirmed. Reload strategies and inspect the fork before trying again; your edits are kept."
          : "Publication could not be confirmed. Inspect or reload version history before trying again; your edits are kept.",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <Card title="Edit a copy of these rules">
      <p>{familyText[version.config.signals.kind]}</p>
      <p>
        Your changes stay local until you publish. Selecting another source
        version replaces unsaved edits. Publication preserves the original
        version and does not change portfolio holdings or bindings.
      </p>
      <p>
        Use 0.20 for 20%. Stock/sector caps and cash floors are constraints, not
        forecasts. Family, inverse-volatility allocation, monthly rebalance and
        next-open policy stay as shown in the complete rules; select another
        template for another family.
      </p>
      <form ref={form} onSubmit={(event) => void publish(event)}>
        <fieldset disabled={busy || unavailable} className="strategy-fields">
          <legend className="sr-only">Supported strategy parameters</legend>
          {[...new Set(fields.map((field) => field.group))].map((group) => (
            <fieldset key={group} className="strategy-fieldset">
              <legend>{group}</legend>
              <div className="inspection-form">
                {fields
                  .filter((field) => field.group === group)
                  .map((field) => (
                    <label
                      key={field.path}
                      className={
                        field.type === "checkbox" ? "strategy-check" : ""
                      }
                    >
                      {field.label}
                      <input
                        name={field.path}
                        type={field.type}
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        required={field.type !== "checkbox"}
                        {...(field.type === "checkbox"
                          ? { checked: draft[field.path] === "true" }
                          : { value: draft[field.path] })}
                        onChange={(event) =>
                          setDraft((old) => ({
                            ...old,
                            [field.path]:
                              field.type === "checkbox"
                                ? String(event.target.checked)
                                : event.target.value,
                          }))
                        }
                      />
                    </label>
                  ))}
              </div>
            </fieldset>
          ))}
          <section aria-labelledby="strategy-diff-title">
            <h3 id="strategy-diff-title">Review your changes</h3>
            {invalid ? (
              <p className="notice">{invalid}</p>
            ) : diff.length ? (
              <div
                className="table-scroll"
                role="region"
                aria-label="Rule changes"
                tabIndex={0}
              >
                <table>
                  <caption>
                    Changes from published version {version.version}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Rule</th>
                      <th scope="col">Published</th>
                      <th scope="col">Your change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diff.map((row) => (
                      <tr key={row.label}>
                        <th scope="row">{row.label}</th>
                        <td>{row.before}</td>
                        <td>{row.after}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>
                No rule changes. Publishing still creates a new immutable
                version; a named fork copies these complete rules.
              </p>
            )}
          </section>
          <details>
            <summary>See the complete proposed rules</summary>
            <pre className="evidence-json" tabIndex={0}>
              {invalid
                ? "Finish the fields to prepare complete rules."
                : JSON.stringify(edited, null, 2)}
            </pre>
          </details>
          <div className="strategy-publish">
            <Button type="submit" value="append" disabled={Boolean(invalid)}>
              Publish new version
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setDraft(initialDraft(version.config));
                setError("");
              }}
            >
              Reset unsaved changes
            </Button>
          </div>
          <label className="field-label" htmlFor="strategy-fork-name">
            New strategy name
          </label>
          <input
            id="strategy-fork-name"
            ref={nameInput}
            value={name}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                if (
                  forkSubmit.current &&
                  !forkSubmit.current.matches(":disabled")
                ) {
                  form.current?.requestSubmit(forkSubmit.current);
                }
              }
            }}
            aria-describedby="strategy-fork-help"
          />
          <p id="strategy-fork-help">
            A named fork is a separate strategy. Its name can differ from the
            rule display name above.
          </p>
          <Button
            ref={forkSubmit}
            type="submit"
            value="fork"
            variant="outline"
            disabled={Boolean(invalid)}
          >
            Create named fork
          </Button>
        </fieldset>
        {busy && <p role="status">Publishing your rules…</p>}
        {error && (
          <p role="alert" className="notice notice-error">
            {error}
          </p>
        )}
      </form>
    </Card>
  );
}
