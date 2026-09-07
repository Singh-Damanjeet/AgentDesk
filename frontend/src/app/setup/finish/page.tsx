"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  completeSetup,
  getAISettings,
  getCompanySettings,
} from "@/lib/api";
import { getAIProviderLabel, isAIProvider } from "@/lib/ai-providers";

type StatusRowProps = {
  label: string;
  value: string;
  configured: boolean;
};

function StatusRow({ label, value, configured }: StatusRowProps) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-zinc-400">{label}</span>
      <span className={configured ? "text-emerald-300" : "text-amber-300"}>
        {value}
      </span>
    </div>
  );
}

export default function FinishSetupPage() {
  const router = useRouter();

  const [companyConfigured, setCompanyConfigured] = useState(false);
  const [aiProvider, setAIProvider] = useState<string | null>(null);
  const [aiConfigured, setAIConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [finishing, setFinishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSummary() {
      try {
        const [company, aiProvider] = await Promise.all([
          getCompanySettings(),
          getAISettings(),
        ]);

        if (cancelled) {
          return;
        }

        setCompanyConfigured(Boolean(company?.name.trim()));
        setAIProvider(
          isAIProvider(aiProvider?.provider) ? aiProvider.provider : null,
        );
        setAIConfigured(Boolean(aiProvider?.api_key_configured));
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load setup summary.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSummary();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleFinish() {
    setFinishing(true);
    setError(null);

    try {
      await completeSetup();
      router.replace("/dashboard");
    } catch (finishError) {
      setError(
        finishError instanceof Error
          ? finishError.message
          : "Unable to complete setup.",
      );
    } finally {
      setFinishing(false);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-zinc-950 text-white">
        <div className="mx-auto max-w-3xl px-6 py-20">
          <p className="text-zinc-400">Loading setup summary...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-sm text-zinc-500">Step 5 of 5</p>

        <h1 className="mt-4 text-3xl font-semibold">
          Ready to launch AgentDesk
        </h1>

        <p className="mt-3 max-w-xl text-zinc-400">
          Review the required configuration, then finish setup to open the
          dashboard.
        </p>

        <div className="mt-10 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <div className="space-y-4 text-sm">
            <StatusRow
              label="Company"
              value={companyConfigured ? "Configured" : "Needs configuration"}
              configured={companyConfigured}
            />

            <StatusRow
              label="AI Provider"
              value={
                aiConfigured
                  ? `${getAIProviderLabel(aiProvider)} configured`
                  : "Needs configuration"
              }
              configured={aiConfigured}
            />

            <StatusRow
              label="Storage"
              value="Local SQLite"
              configured
            />
          </div>
        </div>

        {error && (
          <div
            role="alert"
            className="mt-6 rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
          >
            {error}
          </div>
        )}

        <div className="mt-10 flex justify-between">
          <button
            type="button"
            onClick={() => router.push("/setup/storage")}
            disabled={finishing}
            className="rounded-lg border border-zinc-700 px-5 py-3 disabled:opacity-50"
          >
            Back
          </button>

          <button
            type="button"
            onClick={() => void handleFinish()}
            disabled={finishing}
            className="rounded-lg bg-white px-5 py-3 font-medium text-black disabled:opacity-50"
          >
            {finishing ? "Finishing..." : "Finish setup"}
          </button>
        </div>
      </div>
    </main>
  );
}
