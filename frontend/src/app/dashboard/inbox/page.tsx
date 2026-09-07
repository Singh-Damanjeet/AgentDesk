"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import PageHeader from "@/components/dashboard/page-header";
import EmptyState from "@/components/ui/empty-state";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  customerLabel,
  formatTicketDate,
  TicketStatusBadge,
  TICKET_STATUS_OPTIONS,
} from "@/components/dashboard/ticket-ui";
import {
  listTickets,
  type TicketListResponse,
  type TicketStatus,
} from "@/lib/api";

const FILTERS: readonly {
  value: TicketStatus | undefined;
  label: string;
}[] = [
  { value: undefined, label: "All" },
  ...TICKET_STATUS_OPTIONS,
];

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function InboxPage() {
  const [filter, setFilter] = useState<TicketStatus | undefined>();
  const [tickets, setTickets] = useState<TicketListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadTickets() {
      setLoading(true);
      setError(null);

      try {
        const result = await listTickets({ status: filter, limit: 50 });

        if (!cancelled) {
          setTickets(result);
        }
      } catch (loadError) {
        if (!cancelled) {
          setTickets(null);
          setError(getErrorMessage(loadError, "Unable to load tickets."));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadTickets();

    return () => {
      cancelled = true;
    };
  }, [filter, refreshKey]);

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
        eyebrow="Support operations"
        title="Inbox"
        description="Review conversations, follow AI work, and move tickets through the supported lifecycle."
        action={
          <button
            type="button"
            onClick={() => setRefreshKey((current) => current + 1)}
            className="rounded-lg border border-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-100 transition-colors hover:border-zinc-500 hover:bg-zinc-900"
          >
            Refresh
          </button>
        }
      />

      <div className="mt-8 space-y-6">
        <div
          aria-label="Filter tickets by status"
          className="flex gap-2 overflow-x-auto pb-1"
          role="group"
        >
          {FILTERS.map((option) => {
            const active = filter === option.value;

            return (
              <button
                key={option.label}
                type="button"
                aria-pressed={active}
                onClick={() => setFilter(option.value)}
                className={`whitespace-nowrap rounded-lg border px-3 py-2 text-sm transition-colors ${
                  active
                    ? "border-zinc-500 bg-zinc-800 text-white"
                    : "border-zinc-800 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>

        {loading ? (
          <LoadingState label="Loading inbox..." />
        ) : error ? (
          <ErrorState
            title="Inbox unavailable"
            description={error}
            action={retryAction}
          />
        ) : tickets && tickets.items.length === 0 ? (
          <EmptyState
            title={filter ? "No matching tickets" : "Inbox is empty"}
            description={
              filter
                ? "Try another status filter to see more conversations."
                : "Conversations created through the channel-independent API will appear here."
            }
          />
        ) : tickets ? (
          <section
            aria-label="Tickets"
            className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/30"
          >
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-zinc-800 bg-zinc-950/60 text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-5 py-4 font-medium">Ticket</th>
                    <th className="px-5 py-4 font-medium">Customer</th>
                    <th className="px-5 py-4 font-medium">Status</th>
                    <th className="px-5 py-4 font-medium">Messages</th>
                    <th className="px-5 py-4 font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {tickets.items.map((ticket) => (
                    <tr
                      key={ticket.id}
                      className="text-zinc-300 transition-colors hover:bg-zinc-900"
                    >
                      <td className="max-w-md px-5 py-4 align-top">
                        <Link
                          href={`/dashboard/inbox/${ticket.id}`}
                          className="block rounded-md outline-none focus-visible:ring-2 focus-visible:ring-white"
                        >
                          <span className="block font-medium text-white">
                            {ticket.subject || "Untitled conversation"}
                          </span>
                          <span className="mt-1 block truncate text-xs text-zinc-500">
                            {ticket.last_message_preview || "No messages yet"}
                          </span>
                        </Link>
                      </td>
                      <td className="whitespace-nowrap px-5 py-4 align-top text-zinc-400">
                        {customerLabel(ticket.customer)}
                      </td>
                      <td className="whitespace-nowrap px-5 py-4 align-top">
                        <TicketStatusBadge status={ticket.status} />
                      </td>
                      <td className="whitespace-nowrap px-5 py-4 align-top text-zinc-500">
                        {ticket.message_count}
                      </td>
                      <td className="whitespace-nowrap px-5 py-4 align-top text-zinc-500">
                        {formatTicketDate(ticket.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="border-t border-zinc-800 px-5 py-3 text-xs text-zinc-600">
              Showing {tickets.items.length} of {tickets.total} tickets.
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
