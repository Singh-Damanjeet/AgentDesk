import PageHeader from "@/components/dashboard/page-header";
import EmptyState from "@/components/ui/empty-state";

export default function KnowledgePage() {
  return (
    <div>
      <PageHeader
        eyebrow="Support content"
        title="Knowledge Base"
        description="Manage the content that will support future AI responses."
      />
      <div className="mt-8">
        <EmptyState
          title="No knowledge documents yet"
          description="Document ingestion and retrieval are intentionally deferred to a later phase."
        />
      </div>
    </div>
  );
}
