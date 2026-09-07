import WidgetChatShell from "@/components/widget/chat-shell";

type WidgetChatPageProps = {
  searchParams: Promise<{
    project?: string | string[];
  }>;
};

export default async function WidgetChatPage({
  searchParams,
}: WidgetChatPageProps) {
  const params = await searchParams;
  const project = Array.isArray(params.project)
    ? params.project[0]
    : params.project;

  return <WidgetChatShell projectId={project ?? "local-default"} />;
}
