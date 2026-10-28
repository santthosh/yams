"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { createApiClient } from "../api/generated/client";
import type { components } from "../api/generated/schema";
import { Card, EmptyState } from "./evidence";
import { Button } from "./ui/button";
import { VersionEditor } from "./strategy/VersionEditor";
import { familyText } from "./strategy/config-form";

type S = components["schemas"];
export function StrategyBrowser() {
  const [roots, setRoots] = useState<S["StrategyV1"][]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [rootId, setRootId] = useState("");
  const [root, setRoot] = useState<S["StrategyV1"] | null>(null);
  const [versions, setVersions] = useState<S["StrategyVersionV1"][]>([]);
  const [versionCursor, setVersionCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<S["StrategyVersionV1"] | null>(null);
  const [listRevision, setListRevision] = useState(0);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [moreLoading, setMoreLoading] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [message, setMessage] = useState("");
  const [publishing, setPublishing] = useState(false);
  const historyRequest = useRef<AbortController | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    void (async () => {
      try {
        const response = await createApiClient(window.location.origin).GET(
          "/api/v1/strategies",
          { params: { query: { limit: 25 } }, signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (!response.data) throw new Error("unavailable");
        setRoots(response.data.items);
        setCursor(response.data.next_cursor);
        if (!response.data.items.length) {
          setRootId("");
          setRoot(null);
          setSelected(null);
        } else
          setRootId(
            (current) =>
              current ||
              response.data!.items.find(
                (row) => row.template_key === "risk_adjusted_momentum_v1",
              )?.id ||
              response.data!.items[0].id,
          );
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Strategies could not be loaded. Try reloading; no rules have been changed.",
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [listRevision]);
  useEffect(() => {
    if (!rootId) return;
    const controller = new AbortController();
    historyRequest.current = controller;
    void (async () => {
      try {
        const api = createApiClient(window.location.origin);
        const [detail, history] = await Promise.all([
          api.GET("/api/v1/strategies/{strategy_id}", {
            params: { path: { strategy_id: rootId } },
            signal: controller.signal,
          }),
          api.GET("/api/v1/strategies/{strategy_id}/versions", {
            params: { path: { strategy_id: rootId }, query: { limit: 25 } },
            signal: controller.signal,
          }),
        ]);
        if (controller.signal.aborted) return;
        if (!detail.data || !history.data) throw new Error("unavailable");
        setRoot(detail.data);
        setVersions(history.data.items);
        setVersionCursor(history.data.next_cursor);
        setSelected((old) =>
          old?.strategy_id === rootId ? old : detail.data!.published_version,
        );
      } catch {
        if (!controller.signal.aborted)
          setHistoryError(
            "This strategy or its version history is unavailable. Reload history before publishing.",
          );
      } finally {
        if (!controller.signal.aborted) setHistoryLoading(false);
      }
    })();
    return () => controller.abort();
  }, [rootId, historyRevision]);

  async function moreStrategies() {
    if (!cursor || moreLoading) return;
    const signal = lifetime.current?.signal;
    setMoreLoading(true);
    setError("");
    try {
      const response = await createApiClient(window.location.origin).GET(
        "/api/v1/strategies",
        {
          params: { query: { limit: 25, cursor } },
          signal,
        },
      );
      if (signal?.aborted) return;
      if (!response.data) throw new Error("unavailable");
      setRoots((old) => [
        ...new Map(
          [...old, ...response.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      setCursor(response.data.next_cursor);
    } catch {
      if (!signal?.aborted)
        setError(
          "The next strategy page could not be loaded. Your current selection is kept.",
        );
    } finally {
      setMoreLoading(false);
    }
  }
  async function moreVersions() {
    if (!versionCursor || moreLoading) return;
    const signal = historyRequest.current?.signal;
    setMoreLoading(true);
    setHistoryError("");
    try {
      const response = await createApiClient(window.location.origin).GET(
        "/api/v1/strategies/{strategy_id}/versions",
        {
          params: {
            path: { strategy_id: rootId },
            query: { limit: 25, cursor: versionCursor },
          },
          signal,
        },
      );
      if (signal?.aborted) return;
      if (!response.data) throw new Error("unavailable");
      setVersions((old) => [
        ...new Map(
          [...old, ...response.data!.items].map((row) => [row.id, row]),
        ).values(),
      ]);
      setVersionCursor(response.data.next_cursor);
    } catch {
      if (!signal?.aborted)
        setHistoryError(
          "The next version page could not be loaded. Reload history before publishing.",
        );
    } finally {
      setMoreLoading(false);
    }
  }
  function published(
    actualRoot: S["StrategyV1"],
    actualVersion: S["StrategyVersionV1"],
  ) {
    setRoots((old) => [
      ...new Map([...old, actualRoot].map((row) => [row.id, row])).values(),
    ]);
    setRoot(actualRoot);
    setRootId(actualRoot.id);
    setSelected(actualVersion);
    setHistoryLoading(true);
    setHistoryError("");
    setMessage(
      `Published version ${actualVersion.version} of ${actualRoot.name}. The source version is preserved.`,
    );
    setHistoryRevision((value) => value + 1);
  }
  const currentRoot = root?.id === rootId ? root : null;
  const currentVersion = selected?.strategy_id === rootId ? selected : null;
  const choices = [
    ...new Map(
      [
        ...versions.filter((row) => row.strategy_id === rootId),
        ...(currentRoot ? [currentRoot.published_version] : []),
        ...(currentVersion ? [currentVersion] : []),
      ].map((row) => [row.id, row]),
    ).values(),
  ].sort((a, b) => a.version - b.version);
  return (
    <div className="strategy-browser">
      <div className="page-heading">
        <div>
          <p className="eyebrow">EXAMINE THE RULES</p>
          <h1>Strategy Lab</h1>
          <p>
            Explore a baseline, change supported parameters and publish an
            immutable version. Paper only.
          </p>
        </div>
      </div>
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
      <Card title="Choose a strategy">
        <p>
          Stock templates share eligibility, allocation and risk controls. A
          description is a hypothesis, not an investment recommendation.
        </p>
        {loading && <p role="status">Loading strategies…</p>}
        {error && (
          <p role="alert" className="notice notice-error">
            {error}
          </p>
        )}
        {!loading && !roots.length && !error && (
          <EmptyState title="No saved strategies">
            No published templates or forks are available in this workspace.
            Reload after a strategy has been published.
          </EmptyState>
        )}
        <div className="strategy-list" aria-label="Published strategies">
          {roots.map((row) => (
            <article key={row.id} className="strategy-summary">
              <h3>{row.name}</h3>
              <p>{familyText[row.published_version.config.signals.kind]}</p>
              <p>
                {row.is_template ? "Starting template" : "Named fork"} · Latest
                version {row.published_version.version}
              </p>
              <Button
                type="button"
                variant={row.id === rootId ? "default" : "outline"}
                disabled={publishing}
                aria-pressed={row.id === rootId}
                onClick={() => {
                  if (row.id === rootId) return;
                  setHistoryLoading(true);
                  setHistoryError("");
                  setRootId(row.id);
                  setMessage("");
                }}
              >
                Inspect {row.name}
              </Button>
            </article>
          ))}
        </div>
        <div className="strategy-publish">
          <Button
            type="button"
            variant="outline"
            disabled={loading || publishing}
            onClick={() => {
              setLoading(true);
              setError("");
              setListRevision((value) => value + 1);
            }}
          >
            Reload strategies
          </Button>
          {cursor && (
            <Button
              type="button"
              variant="outline"
              disabled={moreLoading || publishing}
              onClick={() => void moreStrategies()}
            >
              Load more strategies
            </Button>
          )}
        </div>
        <p>
          SPY is a benchmark reference. It is not a publishable stock strategy.
        </p>
      </Card>
      {rootId && (
        <Card title="Published version history">
          {historyLoading && <p role="status">Loading version history…</p>}
          {historyError && (
            <p role="alert" className="notice notice-error">
              {historyError}
            </p>
          )}
          <label className="field-label" htmlFor="strategy-version-choice">
            Source version — selecting another replaces unsaved edits
          </label>
          <select
            id="strategy-version-choice"
            value={currentVersion?.id ?? ""}
            disabled={historyLoading || publishing}
            onChange={(event) => {
              const row = choices.find(
                (item) => item.id === event.target.value,
              );
              if (row) {
                setSelected(row);
                setMessage("");
              }
            }}
          >
            {!currentVersion && <option value="">Choose a version</option>}
            {choices.map((row) => (
              <option key={row.id} value={row.id}>
                Version {row.version} · {row.id}
              </option>
            ))}
          </select>
          <div className="strategy-publish">
            <Button
              type="button"
              variant="outline"
              disabled={historyLoading || publishing}
              onClick={() => {
                setHistoryLoading(true);
                setHistoryError("");
                setHistoryRevision((value) => value + 1);
              }}
            >
              Reload history
            </Button>
            {versionCursor && (
              <Button
                type="button"
                variant="outline"
                disabled={moreLoading || publishing || historyLoading}
                onClick={() => void moreVersions()}
              >
                Load more versions
              </Button>
            )}
          </div>
          {currentVersion && (
            <>
              <p>
                Published version {currentVersion.version} ·{" "}
                <time dateTime={currentVersion.published_at}>
                  {currentVersion.published_at}
                </time>
              </p>
              <details>
                <summary>See published rules and identity</summary>
                <p>
                  Version <code>{currentVersion.id}</code>
                </p>
                <p>
                  Config SHA-256 <code>{currentVersion.config_sha256}</code>
                </p>
                <pre className="evidence-json" tabIndex={0}>
                  {JSON.stringify(currentVersion.config, null, 2)}
                </pre>
              </details>
            </>
          )}
        </Card>
      )}
      {currentRoot && currentVersion && (
        <VersionEditor
          key={currentVersion.id}
          strategy={currentRoot}
          version={currentVersion}
          onBusy={setPublishing}
          onPublished={published}
          unavailable={historyLoading || Boolean(historyError)}
        />
      )}
      <p>
        Experiments and comparisons are staged separately.{" "}
        <Link href="/lab/candidates">
          Inspect candidates from a saved version
        </Link>
        .
      </p>
    </div>
  );
}
