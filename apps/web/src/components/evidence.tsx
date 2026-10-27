import type { ReactNode } from "react";
import type { components } from "../api/generated/schema";
import { formatDecimal } from "../lib/format";

type Schema = components["schemas"];
export function Money({
  value,
  locale = "en-US",
}: {
  value: Schema["UniverseConfig"]["min_price_usd"] | null;
  locale?: string;
}) {
  return (
    <span className="tabular-nums">
      {formatDecimal(value, "money", locale)}
    </span>
  );
}
export function ReturnPercent({
  value,
  locale = "en-US",
}: {
  value: Schema["TargetWeight"]["weight"] | null;
  locale?: string;
}) {
  return (
    <span className="tabular-nums">
      {formatDecimal(value, "percent", locale)}
    </span>
  );
}
export function Quantity({
  value,
  locale = "en-US",
}: {
  value: Schema["PaperOrderV1"]["requested_quantity"] | null;
  locale?: string;
}) {
  return (
    <span className="tabular-nums">
      {formatDecimal(value, "quantity", locale)}
    </span>
  );
}
export function Card({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
export function EmptyState({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span aria-hidden="true" className="empty-mark">
        ＋
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function WarningsPanel({
  warnings,
  severity = "warning",
}: {
  warnings: Schema["SnapshotManifestV1"]["warnings"];
  severity?: "warning" | "error";
}) {
  if (!warnings.length) return null;
  return (
    <div
      className={`notice notice-${severity}`}
      role={severity === "error" ? "alert" : "note"}
    >
      <strong>
        {severity === "error" ? "Action required" : "Please note"}
      </strong>
      <ul>
        {warnings.map((warning, index) => (
          <li key={index}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}
export function DataProvenanceBadge({
  mode,
  asOf,
  provider,
  freshness = "unavailable",
}: {
  mode: Schema["SnapshotManifestV1"]["mode"] | null;
  asOf: Schema["SnapshotCoverage"]["last_session"];
  provider?: string;
  freshness?: "fixture" | "current" | "stale" | "unavailable";
}) {
  return (
    <div className="provenance">
      <span className="source-badge">
        {mode === "synthetic_fixture"
          ? "Synthetic demo"
          : mode === "research_market_data"
            ? "Market research data"
            : "Source unavailable"}
      </span>
      <span>As of {asOf ?? "unavailable"}</span>
      <span>
        {freshness === "fixture"
          ? "Fixture calendar · not live market data"
          : freshness === "stale"
            ? "Stale — older evidence"
            : freshness === "current"
              ? "Latest validated session"
              : "Freshness unavailable"}
        {provider ? ` · ${provider}` : ""}
      </span>
    </div>
  );
}
export function VersionIdentity({
  label,
  identity,
}: {
  label: string;
  identity: Schema["JobV1"]["id"] | null;
}) {
  return (
    <div className="identity">
      <span>{label}</span>
      <code>{identity ?? "Unavailable"}</code>
    </div>
  );
}
export function ErrorState({
  correlationId,
  retry,
}: {
  correlationId?: Schema["ErrorDetail"]["correlation_id"];
  retry?: ReactNode;
}) {
  return (
    <div className="notice notice-error" role="alert">
      <h2>Local service unavailable</h2>
      <p>
        The request could not be completed. Check that YAMS is running, then try
        again.
      </p>
      {correlationId && (
        <p className="diagnostic">
          Diagnostic ID: <code>{correlationId}</code>
        </p>
      )}
      {retry}
    </div>
  );
}
export function JobProgress({ job }: { job: Schema["JobV1"] }) {
  const names = {
    queued: "Queued",
    running: "Running",
    cancel_requested: "Cancellation requested",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
  };
  const active =
    job.status === "running" ||
    job.status === "queued" ||
    job.status === "cancel_requested";
  return (
    <div className="job-progress" role="status" aria-live="polite">
      <h3>{names[job.status]}</h3>
      <p>
        Attempt {job.attempts} of {job.max_attempts} · {job.kind}
      </p>
      {active && (
        <>
          <label htmlFor={`progress-${job.id}`}>
            Advisory progress: {job.progress}%
          </label>
          <progress id={`progress-${job.id}`} value={job.progress} max={100} />
        </>
      )}
      <p>
        {job.status === "completed"
          ? "A sealed result is available."
          : job.status === "failed"
            ? "No completed result. Review diagnostics before submitting new work."
            : job.status === "cancelled"
              ? "This job has stopped."
              : "No completed result yet."}
      </p>
      {job.error && (
        <p className="diagnostic">
          {job.error.code} · Diagnostic ID:{" "}
          <code>{job.error.correlation_id}</code>
        </p>
      )}
      <p className="subtle">Updated {job.updated_at}</p>
    </div>
  );
}
