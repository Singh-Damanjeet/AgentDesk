import { getBackendHealth } from "@/lib/api";

export default async function Home() {
  let backendConnected = false;

  try {
    const health = await getBackendHealth();
    backendConnected = health.status === "ok";
  } catch {
    backendConnected = false;
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto max-w-6xl px-6 py-16">
        <p className="text-sm font-medium text-zinc-400">
          AgentDesk
        </p>

        <h1 className="mt-4 text-4xl font-semibold tracking-tight">
          AI Customer Support Platform
        </h1>

        <p className="mt-4 max-w-2xl text-zinc-400">
          Self-hosted AI customer support automation.
        </p>

        <div className="mt-10 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <p className="text-sm text-zinc-400">
            Backend status
          </p>

          <p className="mt-2 font-medium">
            {backendConnected ? "Connected" : "Disconnected"}
          </p>
        </div>
      </div>
    </main>
  );
}