"use client";
import Link from "next/link";
import { useWorkspace } from "./workspace-provider";
import { Card, ErrorState, VersionIdentity, WarningsPanel } from "./evidence";
import { Button } from "./ui/button";
import { PortfolioDashboard } from "./decisions/PortfolioDashboard";
import { JobInspector } from "./job-inspector";

function ServiceState() {
  const { phase, correlationId, refresh, health } = useWorkspace();
  if (phase === "loading")
    return (
      <div className="loading-state" role="status">
        <span className="loading-dot" aria-hidden="true" />
        Initializing local workspace…
      </div>
    );
  if (phase === "error")
    return (
      <ErrorState
        correlationId={correlationId}
        retry={<Button onClick={refresh}>Try again</Button>}
      />
    );
  if (health?.status === "not_ready")
    return (
      <WarningsPanel
        severity="error"
        warnings={[
          "Some local services are not ready. Open Settings & data to inspect the checks. Investment values remain unavailable.",
        ]}
      />
    );
  return null;
}
export function Dashboard() {
  const { health, phase, refresh } = useWorkspace();
  const fixture = health?.fixture_metadata;
  const ready = phase === "ready" && health?.status === "ready";
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">A SPACE TO EXPLORE</p>
          <h1>Your research starts here.</h1>
          <p>Build understanding before putting ideas into motion.</p>
        </div>
        <Button
          variant="outline"
          onClick={refresh}
          disabled={phase === "loading"}
        >
          Refresh status
        </Button>
      </div>
      <ServiceState />
      <div className="dashboard-grid">
        <section className="welcome-card">
          <div>
            <span className="small-label">PAPER RESEARCH, REAL CURIOSITY</span>
            <h2>A clear starting point.</h2>
            <p>
              Your workspace is local. Explore with synthetic data, keep
              evidence in view, and take your time.
            </p>
            <Button asChild>
              <Link href="/settings">
                Explore your workspace <span aria-hidden="true">↗</span>
              </Link>
            </Button>
          </div>
          <div className="abstract-plant" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <i />
          </div>
        </section>
        <Card title="Workspace health">
          <div className="health-value">
            <span
              aria-hidden="true"
              className={`status-dot ${ready ? "is-ready" : ""}`}
            />
            {phase === "loading"
              ? "Checking…"
              : ready
                ? "Ready to explore"
                : "Needs attention"}
          </div>
          <p>
            {ready
              ? "Local storage and bundled fixtures passed their readiness checks."
              : "Readiness has not been confirmed. Check local storage and fixture availability in Settings & data."}
          </p>
          <Link className="text-link" href="/settings">
            View local diagnostics <span aria-hidden="true">→</span>
          </Link>
        </Card>
        <Card title="Your data, in context" className="data-card">
          <div className="card-kicker">
            {fixture ? "SYNTHETIC_DATA_ONLY" : "DATA UNAVAILABLE"}
          </div>
          <dl className="data-facts">
            <div>
              <dt>Source</dt>
              <dd>{fixture ? "Bundled synthetic fixtures" : "Unavailable"}</dd>
            </div>
            <div>
              <dt>Sample assets</dt>
              <dd>{fixture?.asset_count ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Sample coverage</dt>
              <dd>
                {fixture
                  ? `${fixture.first_session} — ${fixture.last_session}`
                  : "Unavailable"}
              </dd>
            </div>
          </dl>
          <p className="subtle">
            Generated examples for offline exploration. These are not returns
            from securities markets.
          </p>
        </Card>
        {ready && <PortfolioDashboard />}
      </div>
      <div className="quiet-note">
        <span aria-hidden="true">↳</span>
        <p>
          YAMS only monitors while it is running. No scheduled analysis happens
          when it is closed.
        </p>
      </div>
    </>
  );
}
export function SettingsView() {
  const { workspace, health, refresh, phase } = useWorkspace();
  const fixture = health?.fixture_metadata;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">LOCAL BY DESIGN</p>
          <h1>Settings & data</h1>
          <Link href="/settings/data">Manage market data and snapshots →</Link>
          <p>A clear view of your workspace and its evidence.</p>
        </div>
        <Button
          variant="outline"
          onClick={refresh}
          disabled={phase === "loading"}
        >
          Refresh status
        </Button>
      </div>
      <ServiceState />
      <div className="settings-grid">
        <Card title="Workspace">
          <dl className="data-facts">
            <div>
              <dt>Display locale</dt>
              <dd>{workspace?.locale ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Default benchmark</dt>
              <dd>{workspace?.default_benchmark ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Application version</dt>
              <dd>0.0.5 · Decision Center</dd>
            </div>
          </dl>
          <VersionIdentity
            label="Workspace ID"
            identity={workspace?.id ?? null}
          />
          <p className="subtle">
            Settings are read-only in this version. No account or sign-in is
            needed.
          </p>
        </Card>
        <Card title="Readiness checks">
          <dl className="readiness-list">
            {(["database", "migration", "workspace", "fixtures"] as const).map(
              (name) => (
                <div key={name}>
                  <dt>
                    {name === "migration"
                      ? "Database schema"
                      : name[0].toUpperCase() + name.slice(1)}
                  </dt>
                  <dd>
                    {health?.[name].status ?? "Unavailable"}
                    {health?.[name].reason && (
                      <span className="reason">{health[name].reason}</span>
                    )}
                  </dd>
                </div>
              ),
            )}
          </dl>
        </Card>
        <Card title="Data source" className="full-width">
          <p>
            {fixture
              ? "Bundled synthetic data is available for offline exploration."
              : "Validated fixture metadata is unavailable."}{" "}
            Open Market data to manage snapshots and optional research sources.
          </p>
          <VersionIdentity
            label="Snapshot ID"
            identity={fixture?.snapshot_id ?? null}
          />
          <VersionIdentity
            label="Manifest SHA-256"
            identity={fixture?.manifest_sha256 ?? null}
          />
          <p className="subtle">
            Fixture dates describe a synthetic calendar. They do not indicate
            current market coverage.
          </p>
        </Card>
        <div className="full-width">
          <JobInspector />
        </div>
      </div>
    </>
  );
}
