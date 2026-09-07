import Link from "next/link";


export default function SetupPage() {
  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto flex min-h-screen max-w-3xl items-center px-6">
        <div className="w-full">
          <p className="text-sm font-medium text-zinc-500">
            AgentDesk Setup
          </p>

          <h1 className="mt-4 text-4xl font-semibold tracking-tight">
            Welcome to AgentDesk
          </h1>

          <p className="mt-4 max-w-xl text-zinc-400">
            Configure your company, AI provider, and local storage
            before starting AgentDesk.
          </p>

          <div className="mt-10 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
            <p className="text-sm text-zinc-500">
              Setup progress
            </p>

            <div className="mt-4 flex flex-wrap gap-3 text-sm">
              <span className="rounded-md bg-white px-3 py-2 text-black">
                Welcome
              </span>

              <span className="rounded-md border border-zinc-700 px-3 py-2 text-zinc-500">
                Company
              </span>

              <span className="rounded-md border border-zinc-700 px-3 py-2 text-zinc-500">
                AI Provider
              </span>

              <span className="rounded-md border border-zinc-700 px-3 py-2 text-zinc-500">
                Storage
              </span>

              <span className="rounded-md border border-zinc-700 px-3 py-2 text-zinc-500">
                Finish
              </span>
            </div>

            <Link
              href="/setup/company"
              className="mt-8 inline-block rounded-lg bg-white px-5 py-3 font-medium text-black"
            >
              Start setup
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}