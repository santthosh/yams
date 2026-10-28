"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { components } from "../api/generated/schema";
import { createApiClient } from "../api/generated/client";
import { Card, EmptyState, WarningsPanel, JobProgress } from "./evidence";
import { Button } from "./ui/button";
import { useWorkspace } from "./workspace-provider";

type S = components["schemas"];
type Mode = S["SnapshotV1"]["mode"];
export function DataSettings() {
  const workspace = useWorkspace();
  const { setJob } = workspace;
  const refreshIdentity = useRef<{ payload: string; key: string } | null>(null);
  const [mode, setMode] = useState<Mode>("synthetic_fixture");
  const [health, setHealth] = useState<S["DataHealthV1"] | null>(null);
  const [snapshots, setSnapshots] = useState<S["SnapshotV1"][]>([]);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [research, setResearch] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState({ query: "", cursor: "" });
  const [assets, setAssets] = useState<S["AssetPageV1"] | null>(null);
  const [assetScope, setAssetScope] = useState("");
  const [assetError, setAssetError] = useState("");
  const visible = health?.mode === mode ? health : null;
  const inventory = snapshots.filter((snapshot) => snapshot.mode === mode);
  const inspected = visible?.current_snapshot ?? inventory[0];
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const client = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    async function load() {
      try {
        const [status, list] = await Promise.all([
          client.GET("/api/v1/data/health", { params: { query: { mode } } }),
          client.GET("/api/v1/data/snapshots", { params: { query: { mode } } }),
        ]);
        if (controller.signal.aborted) return;
        if (!status.data || !list.data) throw new Error("unavailable");
        setHealth(status.data);
        if (status.data.latest_job) setJob(status.data.latest_job);
        setSnapshots(list.data.items);
        setError("");
        if (
          status.data.latest_job &&
          ["queued", "running", "cancel_requested"].includes(
            status.data.latest_job.status,
          )
        )
          timer = setTimeout(() => void load(), 2000);
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Data status is unavailable. Previously loaded data may be out of date.",
          );
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [mode, revision, setJob]);
  const inspectedId = inspected?.id;
  useEffect(() => {
    if (!inspectedId) return;
    const controller = new AbortController();
    const client = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    async function load() {
      try {
        const response = await client.GET("/api/v1/data/assets", {
          params: {
            query: {
              mode,
              snapshot_id: inspectedId!,
              query: search.query,
              cursor: search.cursor || undefined,
            },
          },
        });
        if (controller.signal.aborted) return;
        if (!response.data) throw new Error("unavailable");
        setAssets(response.data);
        setAssetScope(JSON.stringify([mode, inspectedId, search]));
        setAssetError("");
      } catch {
        if (!controller.signal.aborted)
          setAssetError(
            "Asset discovery is unavailable. Try the search again.",
          );
      }
    }
    void load();
    return () => controller.abort();
  }, [mode, inspectedId, search]);
  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const body: S["RefreshPayload"] =
        mode === "synthetic_fixture"
          ? {
              schema_version: 1,
              source_mode: mode,
              expected_manifest_hash:
                workspace.health!.fixture_metadata!.manifest_sha256,
            }
          : {
              schema_version: 1,
              source_mode: mode,
              research_config: JSON.parse(research),
            };
      const serialized = JSON.stringify(body);
      if (refreshIdentity.current?.payload !== serialized)
        refreshIdentity.current = {
          payload: serialized,
          key: crypto.randomUUID(),
        };
      const response = await createApiClient(window.location.origin).POST(
        "/api/v1/data/refresh",
        {
          body,
          params: {
            header: { "Idempotency-Key": refreshIdentity.current.key },
          },
        },
      );
      if (!response.data) throw new Error("unavailable");
      refreshIdentity.current = null;
      workspace.setJob(response.data);
      setRevision((value) => value + 1);
    } catch {
      setError(
        "Refresh could not be queued. Check the source configuration and local services.",
      );
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    setSearch({ query, cursor: "" });
  }
  const shownAssets =
    assets?.mode === mode &&
    assets.snapshot_id === inspected?.id &&
    assetScope === JSON.stringify([mode, inspectedId, search])
      ? assets
      : null;
  const pending =
    visible?.latest_job &&
    ["queued", "running", "cancel_requested"].includes(
      visible.latest_job.status,
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">SETTINGS</p>
          <h1>Market data</h1>
          <p>Inspect source coverage and refresh your local datasets.</p>
        </div>
      </div>
      <Card title="Data source">
        <label htmlFor="data-mode">Source mode</label>{" "}
        <select
          id="data-mode"
          value={mode}
          onChange={(event) => {
            setMode(event.target.value as Mode);
            setSearch({ query: "", cursor: "" });
            setQuery("");
          }}
        >
          <option value="synthetic_fixture">Synthetic sample data</option>
          <option value="research_market_data">Market research data</option>
        </select>
        {mode === "research_market_data" && (
          <details>
            <summary>Research source configuration</summary>
            <p>
              Requires verified local-use permission and supported provider
              coverage. Unverified prices remain inspection-only.
            </p>
            <label htmlFor="research-config">
              Validated research configuration (JSON)
            </label>
            <textarea
              id="research-config"
              rows={8}
              value={research}
              onChange={(event) => setResearch(event.target.value)}
            />
          </details>
        )}
        <p>
          {mode === "synthetic_fixture"
            ? "SYNTHETIC_DATA_ONLY · Sample values are not market returns."
            : "Research mode never substitutes synthetic prices. Freshness is unverified."}
        </p>
        <Button
          onClick={() => void refresh()}
          disabled={
            busy ||
            !!pending ||
            (mode === "synthetic_fixture"
              ? !workspace.health?.fixture_metadata
              : !research.trim())
          }
        >
          {busy ? "Queuing refresh…" : "Refresh selected source"}
        </Button>{" "}
        <Button
          variant="outline"
          onClick={() => setRevision((value) => value + 1)}
        >
          Reload data status
        </Button>
        {error && <p role="alert">{error}</p>}
        {visible?.latest_job && <JobProgress job={visible.latest_job} />}
        {visible?.latest_job?.error && (
          <WarningsPanel
            warnings={[
              visible.latest_job.error.details.reason?.toString() ??
                "Refresh failed. Previous valid data is retained.",
            ]}
          />
        )}
      </Card>
      <Card title="Snapshot coverage">
        {visible?.freshness === "refresh_failed" && (
          <p role="alert">
            Refresh failed. Last valid data is retained and may be stale.
          </p>
        )}
        {!visible && !error ? (
          <p role="status">Loading source coverage…</p>
        ) : inspected ? (
          <>
            <p>
              {inspected.mode === "synthetic_fixture"
                ? "Synthetic sample"
                : "Research observation"}{" "}
              · {inspected.quality}
            </p>
            <dl>
              <dt>Provider</dt>
              <dd>{inspected.provider}</dd>
              <dt>Coverage</dt>
              <dd>
                {inspected.coverage.first_session ?? "Unavailable"} to{" "}
                {inspected.coverage.last_session ?? "Unavailable"}
              </dd>
              <dt>Latest completed data session</dt>
              <dd>{inspected.latest_completed_session ?? "Unavailable"}</dd>
              <dt>Snapshot</dt>
              <dd className="break-all">{inspected.id}</dd>
            </dl>
            <WarningsPanel warnings={inspected.warnings} />
            {!visible?.current_snapshot && (
              <p>
                Inspection only. No usable current snapshot is registered for
                this source.
              </p>
            )}
          </>
        ) : (
          <EmptyState title="No registered snapshot">
            Refresh the selected source to create an immutable dataset. No
            prices are substituted.
          </EmptyState>
        )}
      </Card>
      <Card title="Discover assets">
        <form onSubmit={submit}>
          <label htmlFor="asset-query">Symbol or asset ID</label>{" "}
          <input
            id="asset-query"
            value={query}
            maxLength={120}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Button type="submit" disabled={!inspected}>
            Search assets
          </Button>
        </form>
        {assetError && <p role="alert">{assetError}</p>}
        {shownAssets &&
          (shownAssets.items.length ? (
            <>
              <ul>
                {shownAssets.items.map((asset) => (
                  <li key={asset.asset_id}>
                    {asset.symbol} · {asset.venue} · {asset.sector} ·{" "}
                    {asset.asset_id}
                  </li>
                ))}
              </ul>
              {shownAssets.next_cursor && (
                <Button
                  onClick={() =>
                    setSearch({
                      query: search.query,
                      cursor: shownAssets.next_cursor!,
                    })
                  }
                >
                  Next assets
                </Button>
              )}
            </>
          ) : (
            <EmptyState title="No matching assets">
              Try another symbol or asset ID in this snapshot.
            </EmptyState>
          ))}
      </Card>
    </>
  );
}
