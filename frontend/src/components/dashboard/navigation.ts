export type DashboardNavigationItem = {
  href: string;
  label: string;
  description: string;
};

export const dashboardNavigation: readonly DashboardNavigationItem[] = [
  {
    href: "/dashboard",
    label: "Overview",
    description: "System status and configuration",
  },
  {
    href: "/dashboard/inbox",
    label: "Inbox",
    description: "Support conversations",
  },
  {
    href: "/dashboard/knowledge",
    label: "Knowledge Base",
    description: "Support content and documents",
  },
  {
    href: "/dashboard/widget",
    label: "Website Chat",
    description: "Customer-facing chat widget",
  },
  {
    href: "/dashboard/agent-runs",
    label: "Agent Runs",
    description: "Agent execution history",
  },
  {
    href: "/dashboard/settings",
    label: "Settings",
    description: "Workspace configuration",
  },
];
