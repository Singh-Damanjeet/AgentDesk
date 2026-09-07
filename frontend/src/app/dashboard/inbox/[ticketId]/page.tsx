"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import PageHeader from "@/components/dashboard/page-header";
import {
  customerLabel,
  formatTicketDate,
  TicketStatusBadge,
  TICKET_STATUS_OPTIONS,
} from "@/components/dashboard/ticket-ui";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  getTicket,
  updateTicketStatus,
  type TicketDetail,
  type TicketStatus,
} from "@/lib/api";

const buttonClassName =
  "rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-100 transition-colors hover:border-zinc-500 hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-50";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function senderLabel(senderType: string): string {
  if (senderType === "customer") {
    return "Customer";
  }

  if (senderType === "ai") {
    return "AgentDesk";
  }

  if (senderType === "human") {
    return "Support teammate";
  }

  return "System";
}

export default function TicketDetailPage() {
  const params = useParams<{ ticketId: string }>();
  const ticketId = params.ticketId;
  const [ticket, setTicket] = useState<TicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingStatus, setPendingStatus] = useState<TicketStatus | "">("");

  useEffect(() => {
    let cancelled = false;

    async function loadTicket() {
      if (!ticketId) {
        setError("A ticket identifier is required.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const result = await getTicket(ticketId);

        if (!cancelled) {
          setTicket(result);
        }
      } catch (loadError) {
        if (!cancelled) {
          setTicket(null);
          setError(getErrorMessage(loadError, "Unable to load ticket."));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTicket();

    return () => {
      cancelled = true;
    };
  }, [ticketId]);

  async function handleStatusChange(nextStatus: TicketStatus) {
    if (!ticket || nextStatus === ticket.status) {
      return;
    }

    setPendingStatus(nextStatus);
    setError(null);

    try {
      setTicket(await updateTicketStatus(ticket.id, nextStatus));
    } catch (statusError) {
      setError(
        getErrorMessage(statusError, "Unable to update ticket status."),
      );
    } finally {
      setPendingStatus("");
    }
  }

  if (loading) {
    return <LoadingState label="Loading ticket..." />;
  }

  if (error || !ticket) {
    return (
      <div>
        <PageHeader
          eyebrow="Support operations"
          title="Ticket"
          description="Review the conversation and associated agent trace."
        />
        <div className="mt-8">
          <ErrorState
            title="Ticket unavailable"
            description={error ?? "The requested ticket could not be found."}
            action={
              <Link href="/dashboard/inbox" className={buttonClassName}>
                Back to inbox
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
        eyebrow="Support operations"
        title={ticket.subject || "Untitled conversation"}
        description={`${customerLabel(ticket.customer)} · ${ticket.channel} · Updated ${formatTicketDate(ticket.updated_at)}`}
        action={
          <Link href="/dashboard/inbox" className={buttonClassName}>
            Back to inbox
          </Link>
        }
      />

      <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <main className="min-w-0 space-y-6">
          <section
            aria-label="Ticket metadata"
            className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5"
          >
            <div className="flex flex-wrap items-center gap-3">
              <TicketStatusBadge status={ticket.status} />
              <span className="text-xs uppercase tracking-wide text-zinc-600">
                {ticket.priority} priority
              </span>
            </div>
            <div className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="text-zinc-500">Customer</p>
                <p className="mt-1 text-zinc-200">
                  {customerLabel(ticket.customer)}
                </p>
              </div>
              <div>
                <p className="text-zinc-500">Session</p>
                <p className="mt-1 break-all font-mono text-xs text-zinc-400">
                  {ticket.session_id}
                </p>
              </div>
              <div>
                <label
                  htmlFor="ticket-status"
                  className="block text-zinc-500"
                >
                  Change status
                </label>
                <select
                  id="ticket-status"
                  value={pendingStatus || ticket.status}
                  disabled={pendingStatus !== ""}
                  onChange={(event) =>
                    void handleStatusChange(
                      event.target.value as TicketStatus,
                    )
                  }
                  className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
                >
                  {TICKET_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {error && (
              <p role="alert" className="mt-4 text-sm text-red-300">
                {error}
              </p>
            )}
          </section>

          <section
            aria-label="Conversation"
            className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5"
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
                  Conversation
                </p>
                <h2 className="mt-2 text-lg font-semibold text-white">
                  {ticket.messages.length} messages
                </h2>
              </div>
            </div>

            {ticket.messages.length === 0 ? (
              <p className="mt-6 text-sm text-zinc-500">
                No messages have been recorded for this ticket.
              </p>
            ) : (
              <ol className="mt-6 space-y-4">
                {ticket.messages.map((message) => (
                  <li
                    key={message.id}
                    className={`rounded-xl border p-4 ${
                      message.sender_type === "customer"
                        ? "border-zinc-700 bg-zinc-950/70"
                        : "border-emerald-900/50 bg-emerald-950/10"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium text-zinc-200">
                        {senderLabel(message.sender_type)}
                      </span>
                      <time
                        dateTime={message.created_at}
                        className="text-xs text-zinc-600"
                      >
                        {formatTicketDate(message.created_at)}
                      </time>
                    </div>
                    <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-300">
                      {message.content}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </main>

        <aside className="space-y-6">
          <section
            aria-label="Agent traces"
            className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5"
          >
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              Agent trace
            </p>
            {ticket.agent_runs.length === 0 ? (
              <p className="mt-4 text-sm text-zinc-500">
                No RAG trace is linked to this ticket yet.
              </p>
            ) : (
              <div className="mt-4 space-y-4">
                {ticket.agent_runs.map((run) => (
                  <article
                    key={run.trace_id}
                    className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-zinc-200">
                        {run.model || "RAG run"}
                      </span>
                      <span className="text-xs capitalize text-zinc-500">
                        {run.status}
                      </span>
                    </div>
                    <dl className="mt-4 space-y-2 text-xs">
                      <div className="flex justify-between gap-3">
                        <dt className="text-zinc-600">Trace</dt>
                        <dd className="max-w-[10rem] truncate font-mono text-zinc-400">
                          {run.trace_id}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-3">
                        <dt className="text-zinc-600">Latency</dt>
                        <dd className="text-zinc-400">
                          {run.latency_ms === null
                            ? "-"
                            : `${Math.round(run.latency_ms)} ms`}
                        </dd>
                      </div>
                      {run.retrieval ? (
                        <div className="flex justify-between gap-3">
                          <dt className="text-zinc-600">Retrieved</dt>
                          <dd className="text-zinc-400">
                            {run.retrieval.selected_count} of {run.retrieval.candidate_count}
                          </dd>
                        </div>
                      ) : null}
                    </dl>
                    {run.error ? (
                      <p className="mt-4 rounded-md border border-red-900/60 bg-red-950/20 p-3 text-xs leading-5 text-red-300">
                        {run.error}
                      </p>
                    ) : null}
                    <Link
                      href={`/dashboard/agent-runs/${encodeURIComponent(run.trace_id)}`}
                      className="mt-4 inline-block text-xs font-medium text-zinc-400 underline decoration-zinc-700 underline-offset-4 hover:text-zinc-200"
                    >
                      View full run
                    </Link>
                  </article>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
