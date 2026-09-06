"use client";

import { useEffect, useState } from "react";

import PageHeader from "@/components/dashboard/page-header";
import StatusCard from "@/components/dashboard/status-card";
import EmptyState from "@/components/ui/empty-state";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  getBackendHealth,
  getDashboardOverview,
  type DashboardOverview,
} from "@/lib/api";

type SystemHealth = "healthy" | "unavailable";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function DashboardPage() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [systemHealth, setSystemHealth] =
    useState<SystemHealth>("unavailable");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      setLoading(true);
      setError(null);

      const [overviewResult, healthResult] = await Promise.allSettled([
        getDashboardOverview(),
        getBackendHealth(),
      ]);

      if (cancelled) {
        return;
      }

      if (overviewResult.status === "rejected") {
        setOverview(null);
        setError(
          getErrorMessage(
            overviewResult.reason,
            "Unable to load dashboard overview.",
          ),
        );
      } else {
        setOverview(overviewResult.value);
      }

      if (healthResult.status === "fulfilled") {
        setSystemHealth(
          healthResult.value.status === "ok" ? "healthy" : "unavailable",
        );
      } else {
        // Health is deliberately independent from the other dashboard cards.
        setSystemHealth("unavailable");
      }

      setLoading(false);
    }

    void loadDashboard();

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const retryAction = (
    <button
      type="button"
      onClick={() => setRefreshKey((current) => current + 1)}
      className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900"
    >
      Try again
    </button>
  );

  return (
    <div>
      <PageHeader
        eyebrow="AgentDesk"
        title="Overview"
        description="A live snapshot of your workspace configuration and current support activity."
      />

      <div className="mt-8">
        {loading && <LoadingState label="Loading dashboard overview..." />}

        {!loading && error && (
          <ErrorState
            title="Dashboard unavailable"
            description={error}
            action={retryAction}
          />
        )}

        {!loading && !error && overview && (
          <>
            <section
              aria-label="Dashboard status"
              className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
            >
              <StatusCard
                label="AI Provider"
                value={
                  overview.ai_provider.configured
                    ? "Gemini"
                    : "Not configured"
                }
                description={
                  overview.ai_provider.configured
                    ? (overview.ai_provider.model ?? "Model configured")
                    : "Configure Gemini in Settings."
                }
                tone={overview.ai_provider.configured ? "success" : "warning"}
              />

              <StatusCard
                label="Storage"
                value="Local SQLite"
                description={
                  overview.storage.status === "ready"
                    ? "Ready on this workspace."
                    : "Storage is unavailable."
                }
                tone={
                  overview.storage.status === "ready" ? "success" : "warning"
                }
              />

              <StatusCard
                label="Knowledge Documents"
                value={`${overview.knowledge.document_count}`}
                description="Knowledge ingestion is not available yet."
                tone="neutral"
              />

              <StatusCard
                label="Open Tickets"
                value={`${overview.tickets.open_count}`}
                description={
                  overview.tickets.open_count === 0
                    ? "No open tickets yet."
                    : "Currently open in the workspace."
                }
                tone="neutral"
              />

              <StatusCard
                label="Website Chat"
                value={
                  overview.widget.configured
                    ? "Configured"
                    : "Not configured"
                }
                description="Website chat setup is not available yet."
                tone={overview.widget.configured ? "success" : "neutral"}
              />

              <StatusCard
                label="System Health"
                value={systemHealth === "healthy" ? "Healthy" : "Unavailable"}
                description={
                  systemHealth === "healthy"
                    ? "Backend health check is passing."
                    : "The backend health check could not be reached."
                }
                tone={systemHealth === "healthy" ? "success" : "warning"}
              />
            </section>

            <div className="mt-8">
              <EmptyState
                title="Your support workspace is ready"
                description="Inbox, knowledge workflows, website chat, and agent runs will become available as those phases are implemented."
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
