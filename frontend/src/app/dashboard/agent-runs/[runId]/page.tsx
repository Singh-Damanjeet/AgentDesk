"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import PageHeader from "@/components/dashboard/page-header";
import { formatTicketDate } from "@/components/dashboard/ticket-ui";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import { getAgentRun, type AgentRunDetail } from "@/lib/api";

const linkClassName =
  "text-sm font-medium text-zinc-200 underline decoration-zinc-700 underline-offset-4 transition-colors hover:text-white hover:decoration-zinc-400";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to load agent run.";
}

export default function AgentRunDetailPage() {
  const params = useParams<{ runId: string }>();
  const identifier = params.runId;
  const [run, setRun] = useState<AgentRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function loadRun() {
      if (!identifier) {
        setError("An agent run identifier is required.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const response = await getAgentRun(identifier);
        if (!cancelled) {
          setRun(response);
        }
      } catch (loadError) {
        if (!cancelled) {
          setRun(null);
          setError(errorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadRun();

    return () => {
      cancelled = true;
    };
  }, [identifier]);

  if (loading) {
    return <LoadingState label="Loading agent run..." />;
  }

  if (error || !run) {
    return (
      <div>
        <PageHeader
          eyebrow="Automation"
          title="Agent run"
          description="Review the ordered execution trace for a support response."
        />
        <div className="mt-8">
          <ErrorState
            title="Agent run unavailable"
            description={error ?? "The requested agent run could not be found."}
            action={
              <Link href="/dashboard/agent-runs" className={linkClassName}>
                Back to agent runs
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Automation"
        title="Agent run"
        description={`${run.status} · ${run.provider || "No provider"} · ${run.model || "No model"}`}
        action={
          <Link href="/dashboard/agent-runs" className={linkClassName}>
            Back to agent runs
          </Link>
        }
      />

      <div className="mt-8 space-y-6">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5">
          <dl className="grid gap-5 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-zinc-600">Trace</dt>
              <dd className="mt-1 break-all font-mono text-xs text-zinc-300">
                {run.trace_id}
              </dd>
            </div>
            <div>
              <dt className="text-zinc-600">Started</dt>
              <dd className="mt-1 text-zinc-300">
                {formatTicketDate(run.started_at)}
              </dd>
            </div>
            <div>
              <dt className="text-zinc-600">Latency</dt>
              <dd className="mt-1 text-zinc-300">
                {run.latency_ms === null
                  ? "-"
                  : `${Math.round(run.latency_ms)} ms`}
              </dd>
            </div>
            <div>
              <dt className="text-zinc-600">Ticket</dt>
              <dd className="mt-1">
                {run.ticket_id ? (
                  <Link
                    href={`/dashboard/inbox/${encodeURIComponent(run.ticket_id)}`}
                    className={linkClassName}
                  >
                    Open ticket
                  </Link>
                ) : (
                  <span className="text-zinc-400">Standalone RAG query</span>
                )}
              </dd>
            </div>
          </dl>
          {run.error ? (
            <p className="mt-5 rounded-lg border border-red-900/60 bg-red-950/20 p-4 text-sm leading-6 text-red-300">
              {run.error}
            </p>
          ) : null}
        </section>

        <section
          aria-label="Agent run steps"
          className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5"
        >
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              Ordered steps
            </p>
            <h2 className="mt-2 text-lg font-semibold text-white">
              {run.steps.length} steps recorded
            </h2>
          </div>
          <ol className="mt-6 space-y-4">
            {run.steps.map((step) => (
              <li
                key={step.id}
                className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-800 text-xs font-medium text-zinc-300">
                      {step.sequence_number}
                    </span>
                    <h3 className="text-sm font-medium capitalize text-zinc-200">
                      {step.step_type.replaceAll("_", " ")}
                    </h3>
                  </div>
                  <span className="text-xs text-zinc-600">
                    {step.duration_ms === null
                      ? "-"
                      : `${Math.round(step.duration_ms)} ms`}
                  </span>
                </div>
                <p className="mt-4 text-sm leading-6 text-zinc-400">
                  {step.output_summary || "No step summary recorded."}
                </p>
                {step.metadata ? (
                  <pre className="mt-4 overflow-x-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs leading-5 text-zinc-500">
                    {JSON.stringify(step.metadata, null, 2)}
                  </pre>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
