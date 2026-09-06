import PageHeader from "@/components/dashboard/page-header";
import EmptyState from "@/components/ui/empty-state";

export default function AgentRunsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Automation"
        title="Agent Runs"
        description="Inspect execution history and the steps taken by support agents."
      />
      <div className="mt-8">
        <EmptyState
          title="No agent runs yet"
          description="Agent workflows and run history are intentionally deferred to a later phase."
        />
      </div>
    </div>
  );
}
