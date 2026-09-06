import PageHeader from "@/components/dashboard/page-header";
import EmptyState from "@/components/ui/empty-state";

export default function InboxPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Support operations"
        title="Inbox"
        description="A focused place for conversations and ticket work."
      />
      <div className="mt-8">
        <EmptyState
          title="Inbox is not available yet"
          description="Ticket and conversation workflows are intentionally deferred to a later phase."
        />
      </div>
    </div>
  );
}
