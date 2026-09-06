import PageHeader from "@/components/dashboard/page-header";
import EmptyState from "@/components/ui/empty-state";

export default function WebsiteChatPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Customer experience"
        title="Website Chat"
        description="Configure the customer-facing chat experience for your website."
      />
      <div className="mt-8">
        <EmptyState
          title="Website Chat is not configured"
          description="The embeddable widget and its configuration workflow are intentionally deferred to a later phase."
        />
      </div>
    </div>
  );
}
