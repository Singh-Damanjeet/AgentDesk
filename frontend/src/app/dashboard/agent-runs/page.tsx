"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import EmptyState from "@/components/ui/empty-state";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import PageHeader from "@/components/dashboard/page-header";
import { formatTicketDate } from "@/components/dashboard/ticket-ui";
import { listAgentRuns, type AgentRunListResponse } from "@/lib/api";

const linkClassName =
  "text-sm font-medium text-zinc-200 underline decoration-zinc-700 underline-offset-4 transition-colors hover:text-white hover:decoration-zinc-400";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to load agent runs.";
}

export default function AgentRunsPage() {
  const [result, setResult] = useState<AgentRunListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadRuns() {
      setLoading(true);
      setError(null);

      try {
        const response = await listAgentRuns({ limit: 50 });
        if (!cancelled) {
          setResult(response);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(errorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadRuns();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="Automation"
        title="Agent Runs"
        description="Inspect execution history and the ordered steps taken by support agents."
      />

      <div className="mt-8">
        {loading ? <LoadingState label="Loading agent runs..." /> : null}

        {!loading && error ? (
          <ErrorState
            title="Agent runs unavailable"
            description={error}
          />
        ) : null}

        {!loading && !error && result?.items.length === 0 ? (
          <EmptyState
            title="No agent runs yet"
            description="Agent traces will appear here after a conversation or website-widget message is processed."
          />
        ) : null}

        {!loading && !error && result && result.items.length > 0 ? (
          <section
            aria-label="Agent run history"
            className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/30"
          >
            <div className="hidden grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_8rem_8rem] gap-4 border-b border-zinc-800 px-5 py-3 text-xs font-medium uppercase tracking-[0.16em] text-zinc-600 md:grid">
              <span>Trace</span>
              <span>Provider / model</span>
              <span>Status</span>
              <span>Steps</span>
            </div>
            <div className="divide-y divide-zinc-800">
              {result.items.map((run) => (
                <article
                  key={run.id}
                  className="grid gap-4 px-5 py-5 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_8rem_8rem] md:items-center"
                >
                  <div className="min-w-0">
                    <Link
                      href={`/dashboard/agent-runs/${encodeURIComponent(run.trace_id)}`}
                      className={linkClassName}
                    >
                      <span className="block truncate font-mono text-xs">
                        {run.trace_id}
                      </span>
                    </Link>
                    <p className="mt-2 text-xs text-zinc-600">
                      Started {formatTicketDate(run.started_at)}
                    </p>
                    {run.ticket_id ? (
                      <Link
                        href={`/dashboard/inbox/${encodeURIComponent(run.ticket_id)}`}
                        className="mt-2 inline-block text-xs text-zinc-500 underline decoration-zinc-800 underline-offset-4 hover:text-zinc-300"
                      >
                        View ticket
                      </Link>
                    ) : null}
                  </div>
                  <div className="text-sm text-zinc-300">
                    <p>{run.provider || "No provider"}</p>
                    <p className="mt-1 text-xs text-zinc-600">
                      {run.model || "No model recorded"}
                    </p>
                  </div>
                  <div className="text-sm capitalize text-zinc-400">
                    {run.status}
                    {run.error ? (
                      <p className="mt-1 text-xs text-red-300">Failed</p>
                    ) : null}
                  </div>
                  <div className="text-sm text-zinc-400">
                    <p>{run.step_count} recorded</p>
                    <p className="mt-1 text-xs text-zinc-600">
                      {run.latency_ms === null
                        ? "Latency unavailable"
                        : `${Math.round(run.latency_ms)} ms`}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
