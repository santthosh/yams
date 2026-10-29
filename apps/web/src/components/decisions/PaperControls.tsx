"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState } from "react";
import { createApiClient } from "../../api/generated/client";
import type { components } from "../../api/generated/schema";
import { UUID_PATTERN } from "../../lib/validation";
import { Card, Money, Quantity } from "../evidence";
import { OrderBatchState } from "../portfolios/OrderBatchState";
import { Button } from "../ui/button";
type S = components["schemas"];
type StoredApproval = { key: string; expected_revision: number };
const api = () => createApiClient(window.location.origin);
export function PaperControls({
  decision: d,
  refresh,
  initialBatchId,
  recommendationId,
}: {
  decision: S["RecommendationDetailV1"] | null;
  refresh: () => void;
  initialBatchId: string | null;
  recommendationId: string | null;
}) {
  const [batch, setBatch] = useState<S["PaperBatchDetailV1"] | null>(null);
  const [batchId, setBatchId] = useState<string | null>(initialBatchId);
  const [preview, setPreview] = useState<S["ApprovalPreviewV1"] | null>(null);
  const [attempt, setAttempt] = useState<StoredApproval | null>(null);
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [epoch, setEpoch] = useState(0);
  const locked = useRef(false);
  const identity = recommendationId ?? d?.id;
  const savedKey = identity ? `yams:approval:v1:${identity}` : "";
  useEffect(() => {
    let live = true;
    if (!identity) return;
    void (async () => {
      try {
        const raw = localStorage.getItem(savedKey);
        if (raw) {
          const a = JSON.parse(raw) as StoredApproval;
          if (
            !UUID_PATTERN.test(a.key) ||
            !Number.isSafeInteger(a.expected_revision) ||
            a.expected_revision < 1
          )
            throw new Error("Invalid stored approval");
          if (live) {
            setAttempt(a);
            setUncertain(true);
          }
          const recovered = await api().GET(
            "/api/v1/recommendations/{recommendation_id}/apply-result",
            {
              params: {
                path: { recommendation_id: identity },
                header: { "Idempotency-Key": a.key },
              },
            },
          );
          if (live && recovered.data) {
            setBatchId(recovered.data.batch_id);
            setUncertain(false);
          }
        }
        const result = await api().GET(
          "/api/v1/recommendations/{recommendation_id}/approval-preview",
          { params: { path: { recommendation_id: identity } } },
        );
        if (live) setPreview(result.data ?? null);
      } catch {
        if (live) {
          setStorageBlocked(true);
          setError(
            "Approval context or saved request is unavailable. Reload to recover; do not create a replacement request.",
          );
        }
      }
    })();
    return () => {
      live = false;
    };
  }, [d, identity, savedKey]);
  useEffect(() => {
    const identity = batchId ?? initialBatchId;
    if (!identity) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    void (async () => {
      try {
        const result = await api().GET("/api/v1/order-batches/{batch_id}", {
          params: { path: { batch_id: identity } },
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        if (!result.data) throw new Error("Batch unavailable");
        setBatch(result.data);
        if (!result.data.terminal)
          timer = setTimeout(() => setEpoch((v) => v + 1), 2000);
      } catch {
        if (!controller.signal.aborted)
          setError(
            "Batch state is unavailable. No new fill is implied; refresh to inspect the server.",
          );
      }
    })();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [batchId, initialBatchId, epoch]);
  async function approve() {
    if (!d || storageBlocked || locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    try {
      const a = attempt ?? {
        key: crypto.randomUUID(),
        expected_revision: d.portfolio_revision,
      };
      if (!Number.isSafeInteger(a.expected_revision))
        throw new Error(
          "Revision exceeds browser safety; approval unavailable",
        );
      // Persist BEFORE the first POST; storage failure must prevent submission.
      localStorage.setItem(savedKey, JSON.stringify(a));
      setAttempt(a);
      const prior = await api().GET(
        "/api/v1/recommendations/{recommendation_id}/apply-result",
        {
          params: {
            path: { recommendation_id: d.id },
            header: { "Idempotency-Key": a.key },
          },
        },
      );
      if (prior.data) {
        setBatchId(prior.data.batch_id);
        setUncertain(false);
        setOpen(false);
        refresh();
        return;
      }
      if (prior.response.status !== 404)
        throw new Error("Original approval could not be reconciled");
      const result = await api().POST(
        "/api/v1/recommendations/{recommendation_id}/apply",
        {
          params: {
            path: { recommendation_id: d.id },
            header: { "Idempotency-Key": a.key },
          },
          body: { expected_revision: a.expected_revision },
        },
      );
      if (!result.data) {
        if (result.response.status < 500) {
          setUncertain(false);
          setError(
            result.error?.error.message ??
              "Account or source changed. Refresh and review again.",
          );
          refresh();
          return;
        }
        throw new Error("Unconfirmed approval");
      }
      setBatchId(result.data.batch_id);
      setUncertain(false);
      setOpen(false);
      refresh();
    } catch {
      setUncertain(true);
      setError(
        "Approval outcome unconfirmed. Recover or retry the same saved request; holdings below remain server records.",
      );
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  async function action(kind: "dismiss" | "cancel" | "advance") {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    try {
      if (kind === "dismiss" && d) {
        const r = await api().POST(
          "/api/v1/recommendations/{recommendation_id}/dismiss",
          { params: { path: { recommendation_id: d.id } }, body: {} },
        );
        if (!r.data) throw new Error(r.error?.error.message);
        refresh();
      } else if (batch && kind === "cancel") {
        const r = await api().POST("/api/v1/order-batches/{batch_id}/cancel", {
          params: { path: { batch_id: batch.id } },
          body: {},
        });
        if (!r.data) throw new Error(r.error?.error.message);
        setEpoch((v) => v + 1);
        refresh();
      } else if (batch && kind === "advance") {
        const storage = `yams:fixture-step:v1:${batch.id}`;
        const key = localStorage.getItem(storage) ?? crypto.randomUUID();
        if (!UUID_PATTERN.test(key)) throw new Error("Invalid stored step key");
        localStorage.setItem(storage, key);
        const r = await api().POST(
          "/api/v1/order-batches/{batch_id}/advance-fixture",
          {
            params: {
              path: { batch_id: batch.id },
              header: { "Idempotency-Key": key },
            },
            body: {},
          },
        );
        if (!r.data)
          throw new Error(
            r.error?.error.message ??
              "Step unconfirmed; retry uses the original key",
          );
        // The accepted response confirms this original step. A later explicit
        // click can create the next step after the server reports no active job.
        // Response loss throws before removal, retaining the original key.
        localStorage.removeItem(storage);
        setEpoch((v) => v + 1);
        refresh();
      }
    } catch (e) {
      setError(
        e instanceof Error && e.message
          ? e.message
          : "Action unconfirmed. Refresh or retry the original action.",
      );
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  return (
    <Card title="4. Paper authorization and posted fills">
      <p>
        Paper only. Preview and approval never post holdings. Execution waits
        for an eligible opening and available verified bars; a pending order is
        not a fill.
      </p>
      {error && !open && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      {d && (
        <>
          {!d.is_current && (
            <p role="status" className="notice notice-warning">
              Decision {d.status};{" "}
              {d.stale_reasons.join(", ") || "not currently eligible"}. Original
              evidence is retained. Generate a fresh review when state changes.
            </p>
          )}
          {preview?.unavailable_reason && (
            <p>
              Approval unavailable:{" "}
              {preview.unavailable_reason.replaceAll("_", " ")}
            </p>
          )}
          <div className="portfolio-actions">
            <Dialog.Root open={open} onOpenChange={setOpen}>
              <Dialog.Trigger asChild>
                <Button
                  disabled={
                    busy ||
                    storageBlocked ||
                    !!batch ||
                    (!uncertain &&
                      (!d.is_current ||
                        !preview ||
                        !!preview.unavailable_reason))
                  }
                >
                  {uncertain
                    ? "Recover saved approval"
                    : "Review paper approval"}
                </Button>
              </Dialog.Trigger>
              <Dialog.Portal>
                <Dialog.Overlay className="dialog-overlay" />
                <Dialog.Content className="dialog-content decision-confirm">
                  <Dialog.Title>Confirm paper authorization</Dialog.Title>
                  <Dialog.Description>
                    Authorize synthetic orders only. Cash and holdings change
                    only when durable fills post. An indicative session is not
                    reserved; the server revalidates approval.
                  </Dialog.Description>
                  <p>
                    Portfolio <code>{d.portfolio_id}</code> · Revision{" "}
                    {attempt?.expected_revision ?? d.portfolio_revision}
                  </p>
                  <p>
                    Strategy version <code>{d.strategy_version_id}</code> ·
                    As-of {d.as_of_session}
                  </p>
                  <p>
                    Estimated cost{" "}
                    <Money value={d.estimated_total_trade_cost_usd} /> ·
                    Indicative eligible opening{" "}
                    {preview?.indicative_eligible_open_at ?? "Unavailable"}
                  </p>
                  <ul>
                    {d.actions
                      .filter((a) => a.side !== "HOLD")
                      .map((a) => (
                        <li key={a.asset_id}>
                          {a.side} {a.asset_id} ·{" "}
                          <Quantity value={a.estimated_quantity} /> estimated
                          shares
                        </li>
                      ))}
                  </ul>
                  {error && (
                    <p role="alert" className="notice notice-error">
                      {error}
                    </p>
                  )}
                  <Button disabled={busy} onClick={() => void approve()}>
                    {busy
                      ? "Reconciling authorization…"
                      : uncertain
                        ? "Recover or retry original authorization"
                        : "Authorize paper orders"}
                  </Button>
                  <Dialog.Close asChild>
                    <Button variant="outline" disabled={busy}>
                      Back to review
                    </Button>
                  </Dialog.Close>
                </Dialog.Content>
              </Dialog.Portal>
            </Dialog.Root>
            <Button
              variant="outline"
              disabled={
                busy ||
                uncertain ||
                d.status === "applied" ||
                d.status === "dismissed"
              }
              onClick={() => void action("dismiss")}
            >
              Dismiss decision
            </Button>
          </div>
        </>
      )}
      {batch && (
        <>
          <OrderBatchState batch={batch} />
          <p>
            Fixture observation {batch.fixture_clock_at ?? "Not applicable"} ·
            Fill job {batch.latest_fill_job?.status ?? "None"}
          </p>
          <p>
            Actual operator audit{" "}
            {batch.operator_recorded_at ?? "Legacy audit not recorded"}
          </p>
          {!batch.terminal && (
            <div className="portfolio-actions">
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void action("cancel")}
              >
                Cancel remaining paper orders
              </Button>
              {batch.data_status === "synthetic_fixture" && (
                <Button
                  disabled={busy || !batch.can_advance_fixture}
                  onClick={() => void action("advance")}
                >
                  Observe next fixture close explicitly
                </Button>
              )}
            </div>
          )}
          {batch.advance_unavailable_reason && !batch.terminal && (
            <p>{batch.advance_unavailable_reason.replaceAll("_", " ")}</p>
          )}
          <p>
            Cancellation preserves posted fills. Explicit replay can remain
            pending when the original quote is not yet available. Refresh posted
            state after a fill.
          </p>
        </>
      )}
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          setEpoch((v) => v + 1);
          refresh();
        }}
      >
        Refresh authorization and posted state
      </Button>
    </Card>
  );
}
