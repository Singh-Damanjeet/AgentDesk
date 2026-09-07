import type { TicketStatus } from "@/lib/api";

export const TICKET_STATUS_OPTIONS: readonly {
  value: TicketStatus;
  label: string;
}[] = [
  { value: "open", label: "Open" },
  { value: "ai_processing", label: "AI processing" },
  { value: "waiting_customer", label: "Waiting customer" },
  { value: "human_review", label: "Human review" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const statusClasses: Record<TicketStatus, string> = {
  open: "border-sky-900/70 bg-sky-950/30 text-sky-300",
  ai_processing: "border-violet-900/70 bg-violet-950/30 text-violet-300",
  waiting_customer:
    "border-amber-900/70 bg-amber-950/30 text-amber-300",
  human_review: "border-orange-900/70 bg-orange-950/30 text-orange-300",
  resolved: "border-emerald-900/70 bg-emerald-950/30 text-emerald-300",
  closed: "border-zinc-700 bg-zinc-900 text-zinc-400",
};

export function ticketStatusLabel(status: TicketStatus): string {
  return (
    TICKET_STATUS_OPTIONS.find((option) => option.value === status)?.label ??
    status
  );
}

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusClasses[status]}`}
    >
      {ticketStatusLabel(status)}
    </span>
  );
}

export function customerLabel(
  customer: { name: string | null; email: string | null } | null,
): string {
  if (!customer) {
    return "Anonymous";
  }

  return customer.name || customer.email || "Known customer";
}

export function formatTicketDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
