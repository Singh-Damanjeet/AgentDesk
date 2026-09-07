import { redirect } from "next/navigation";

import { getConfigStatus } from "@/lib/api";

export default async function Home() {
  let configured: boolean;

  try {
    const config = await getConfigStatus();
    configured = config.configured;
  } catch {
    return (
      <main className="min-h-screen bg-zinc-950 text-white">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <p className="text-sm text-zinc-500">AgentDesk</p>

          <h1 className="mt-4 text-4xl font-semibold">Backend unavailable</h1>

          <p className="mt-4 text-zinc-400">
            Start the AgentDesk backend and refresh this page.
          </p>
        </div>
      </main>
    );
  }

  if (configured) {
    redirect("/dashboard");
  }

  redirect("/setup");
}
