"use client";

import { useRouter } from "next/navigation";


export default function StorageSetupPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-sm text-zinc-500">
          Step 4 of 5
        </p>

        <h1 className="mt-4 text-3xl font-semibold">
          Storage
        </h1>

        <p className="mt-3 text-zinc-400">
          Choose how AgentDesk stores its local application data.
        </p>

        <div className="mt-10 rounded-xl border border-zinc-700 bg-zinc-900 p-6">
          <div className="flex items-start gap-4">
            <input
              type="radio"
              checked
              readOnly
              className="mt-1"
            />

            <div>
              <h2 className="font-medium">
                Local storage
              </h2>

              <p className="mt-2 text-sm text-zinc-400">
                AgentDesk will use SQLite on this machine.
              </p>

              <p className="mt-2 text-xs text-zinc-500">
                PostgreSQL support will be available in a later release.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-10 flex justify-between">
          <button
            type="button"
            onClick={() =>
              router.push("/setup/ai-provider")
            }
            className="rounded-lg border border-zinc-700 px-5 py-3"
          >
            Back
          </button>

          <button
            type="button"
            onClick={() =>
              router.push("/setup/finish")
            }
            className="rounded-lg bg-white px-5 py-3 font-medium text-black"
          >
            Continue
          </button>
        </div>
      </div>
    </main>
  );
}