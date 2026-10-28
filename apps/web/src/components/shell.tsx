"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";
import { useWorkspace } from "./workspace-provider";
import { DataProvenanceBadge } from "./evidence";
import { Button } from "./ui/button";

function Navigation() {
  const path = usePathname();
  return (
    <nav aria-label="Main navigation">
      {[
        { path: "/", name: "Dashboard", mark: "01" },
        { path: "/settings", name: "Settings & data", mark: "02" },
      ].map((item) => (
        <Link
          key={item.path}
          href={item.path}
          aria-current={path === item.path ? "page" : undefined}
        >
          <span aria-hidden="true">{item.mark}</span>
          {item.name}
        </Link>
      ))}
    </nav>
  );
}
export function Shell({ children }: { children: ReactNode }) {
  const { health, job } = useWorkspace();
  const pathname = usePathname();
  const fixture = health?.fixture_metadata;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link href="/" className="brand" aria-label="YAMS home">
          <span className="brand-icon" aria-hidden="true">
            y
          </span>
          yams
          <span className="brand-dot" aria-hidden="true">
            .
          </span>
        </Link>
        <p className="sidebar-caption">YOUR RESEARCH WORKSPACE</p>
        <Navigation />
        <div className="sidebar-bottom">
          <span className="paper-badge">Paper only</span>
          <p>
            Invest fake.
            <br />
            <strong>Learn real.</strong>
          </p>
          <span>Local · Single-user</span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="mobile-brand">yams.</div>
          <div className="topbar-label">
            Your local workspace{" "}
            <span className="version-badge">0.0.1 · Foundation</span>
          </div>
          <span className="paper-badge">Paper only</span>
        </header>
        <details className="mobile-nav" key={pathname}>
          <summary>Navigation</summary>
          <Navigation />
        </details>
        <div className="context-bar">
          {pathname === "/settings/data" ? (
            <span>Dataset coverage · Selected source below</span>
          ) : (
            <DataProvenanceBadge
              mode={fixture ? "synthetic_fixture" : null}
              asOf={fixture?.last_session ?? null}
              freshness={fixture ? "fixture" : "unavailable"}
            />
          )}
          <Link className="job-link" href="/settings#job-status">
            {job
              ? `Last checked job: ${job.status.replaceAll("_", " ")}`
              : "Jobs: no job selected"}
          </Link>
        </div>
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="workspace-footer">
          <span>Yet Another Market Simulator</span>
          <Dialog.Root>
            <Dialog.Trigger asChild>
              <Button variant="ghost">About paper research</Button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="dialog-overlay" />
              <Dialog.Content className="dialog-content">
                <Dialog.Title>Room to learn, without real trades.</Dialog.Title>
                <Dialog.Description>
                  YAMS is a local research workspace. Capital and orders are
                  synthetic. It never connects to a brokerage or trades real
                  money. Synthetic fixtures are examples, not market evidence.
                </Dialog.Description>
                <p>
                  Monitoring pauses whenever YAMS is stopped. Historical results
                  and scenarios do not promise future returns.
                </p>
                <Dialog.Close asChild>
                  <Button>Got it</Button>
                </Dialog.Close>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        </footer>
      </div>
    </div>
  );
}
