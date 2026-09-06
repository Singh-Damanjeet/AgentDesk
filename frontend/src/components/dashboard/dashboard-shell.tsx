import type { ReactNode } from "react";

import DashboardSidebar from "./sidebar";

type DashboardShellProps = {
  children: ReactNode;
};

export default function DashboardShell({ children }: DashboardShellProps) {
  return (
    <div className="min-h-screen bg-zinc-950 text-white md:flex">
      <DashboardSidebar />
      <main className="min-w-0 flex-1">
        <div className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-10">
          {children}
        </div>
      </main>
    </div>
  );
}
