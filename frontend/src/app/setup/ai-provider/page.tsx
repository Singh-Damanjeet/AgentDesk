"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getAISettings,
  testAIConnection,
  updateAISettings,
} from "@/lib/api";

const PROVIDER = "gemini";

const MODEL_OPTIONS = [
  {
    value: "gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
  },
  {
    value: "gemini-2.5-pro",
    label: "Gemini 2.5 Pro",
  },
];

export default function AIProviderSetupPage() {
  const router = useRouter();

  const [model, setModel] = useState(MODEL_OPTIONS[0].value);
  const [apiKey, setApiKey] = useState("");
  const [existingKey, setExistingKey] = useState(false);
  const [tested, setTested] = useState(false);

  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);

  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSettings() {
      try {
        const settings = await getAISettings();

        if (cancelled) {
          return;
        }

        if (settings) {
          setModel(settings.model);
          setExistingKey(settings.api_key_configured);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load AI provider settings.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSettings();

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleTest() {
    const normalizedApiKey = apiKey.trim();

    if (!normalizedApiKey) {
      setError("Enter a Gemini API key before testing.");
      setMessage(null);
      return;
    }

    setTesting(true);
    setError(null);
    setMessage(null);
    setTested(false);

    try {
      const result = await testAIConnection({
        provider: PROVIDER,
        api_key: normalizedApiKey,
        model,
      });

      if (result.success) {
        setTested(true);
        setMessage(result.message);
      } else {
        setError(result.message);
      }
    } catch (testError) {
      setError(
        testError instanceof Error
          ? testError.message
          : "Connection test failed.",
      );
    } finally {
      setTesting(false);
    }
  }

  async function saveSettings(allowUntested: boolean) {
    const normalizedApiKey = apiKey.trim();
    const keepingExistingKey = existingKey && !normalizedApiKey;

    if (!normalizedApiKey && !keepingExistingKey) {
      setError("Enter a Gemini API key before continuing.");
      setMessage(null);
      return;
    }

    if (normalizedApiKey && !tested && !allowUntested) {
      setError(
        "Test the connection first, or explicitly save without testing.",
      );
      setMessage(null);
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      await updateAISettings({
        provider: PROVIDER,
        model,
        api_key: normalizedApiKey || undefined,
        embedding_provider: "local",
        embedding_model: null,
        enabled: true,
      });

      router.push("/setup/storage");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Unable to save Gemini settings.",
      );
    } finally {
      setSaving(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void saveSettings(false);
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-zinc-950 text-white">
        <div className="mx-auto max-w-3xl px-6 py-20">
          <p className="text-zinc-400">Loading AI provider settings...</p>
        </div>
      </main>
    );
  }

  const hasNewApiKey = apiKey.trim().length > 0;

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-sm text-zinc-500">Step 3 of 5</p>

        <h1 className="mt-4 text-3xl font-semibold">AI Provider</h1>

        <p className="mt-3 text-zinc-400">
          Configure Google Gemini for AgentDesk.
        </p>

        <form onSubmit={handleSubmit} className="mt-10 space-y-6">
          <div>
            <label
              htmlFor="provider"
              className="text-sm text-zinc-300"
            >
              Provider
            </label>

            <input
              id="provider"
              name="provider"
              value="Google Gemini"
              autoComplete="off"
              disabled
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 text-zinc-400"
            />
          </div>

          <div>
            <label htmlFor="model" className="text-sm text-zinc-300">
              Model
            </label>

            <select
              id="model"
              name="model"
              value={model}
              onChange={(event) => {
                setModel(event.target.value);
                setTested(false);
                setMessage(null);
              }}
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
            >
              {MODEL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="api-key" className="text-sm text-zinc-300">
              Gemini API key
            </label>

            <input
              id="api-key"
              name="api-key"
              type="password"
              value={apiKey}
              autoComplete="new-password"
              spellCheck={false}
              onChange={(event) => {
                setApiKey(event.target.value);
                setTested(false);
                setMessage(null);
              }}
              placeholder={
                existingKey
                  ? "Existing API key is securely stored"
                  : "Enter Gemini API key"
              }
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
            />

            <p className="mt-2 text-xs text-zinc-500">
              {existingKey
                ? "An API key is configured. Leave this field empty to keep it."
                : "The key is encrypted by the backend and is never returned after saving."}
            </p>
          </div>

          <button
            type="button"
            onClick={() => void handleTest()}
            disabled={testing || saving || !hasNewApiKey}
            className="rounded-lg border border-zinc-700 px-5 py-3 text-sm disabled:opacity-50"
          >
            {testing ? "Testing..." : "Test connection"}
          </button>

          {message && (
            <div
              role="status"
              className="rounded-lg border border-emerald-900 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300"
            >
              {message}
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
            >
              {error}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-6">
            <button
              type="button"
              onClick={() => router.push("/setup/company")}
              disabled={testing || saving}
              className="rounded-lg border border-zinc-700 px-5 py-3 disabled:opacity-50"
            >
              Back
            </button>

            <div className="flex gap-3">
              {hasNewApiKey && !tested && (
                <button
                  type="button"
                  onClick={() => void saveSettings(true)}
                  disabled={testing || saving}
                  className="rounded-lg border border-zinc-700 px-5 py-3 text-zinc-300 disabled:opacity-50"
                >
                  Save without testing
                </button>
              )}

              <button
                type="submit"
                disabled={testing || saving}
                className="rounded-lg bg-white px-5 py-3 font-medium text-black disabled:opacity-50"
              >
                {saving ? "Saving..." : "Continue"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </main>
  );
}
