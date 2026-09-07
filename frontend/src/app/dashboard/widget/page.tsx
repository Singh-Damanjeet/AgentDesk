import PageHeader from "@/components/dashboard/page-header";
import WidgetSettingsForm from "@/components/dashboard/widget-settings";

export default function WebsiteChatPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Customer experience"
        title="Website Chat"
        description="Configure the customer-facing chat experience for your website."
      />
      <div className="mt-8">
        <WidgetSettingsForm />
      </div>
    </div>
  );
}
