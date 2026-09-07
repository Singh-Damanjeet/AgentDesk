"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";

import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  API_BASE_URL,
  getWidgetSettings,
  updateWidgetSettings,
  type WidgetPosition,
  type WidgetSettings,
} from "@/lib/api";

const DEFAULT_PROJECT_ID = "local-default";

const inputClassName =
  "mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm text-white outline-none transition-colors focus:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-60";

type WidgetFormState = {
  projectId: string;
  displayName: string;
  welcomeMessage: string;
  position: WidgetPosition;
  enabled: boolean;
  allowedDomains: string;
};

const defaultFormState: WidgetFormState = {
  projectId: DEFAULT_PROJECT_ID,
  displayName: "AgentDesk Support",
  welcomeMessage: "Hi! How can we help?",
  position: "bottom-right",
  enabled: true,
  allowedDomains: "",
};

function settingsToFormState(settings: WidgetSettings): WidgetFormState {
  return {
    projectId: settings.project_id,
    displayName: settings.display_name,
    welcomeMessage: settings.welcome_message,
    position: settings.position,
    enabled: settings.enabled,
    allowedDomains: settings.allowed_domains.join("\n"),
  };
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function parseAllowedDomains(value: string): string[] {
  return value
    .split(/[\r\n,]+/)
    .map((domain) => domain.trim())
    .filter((domain) => domain.length > 0);
}

export default function WidgetSettingsForm() {
  const [form, setForm] = useState<WidgetFormState>(defaultFormState);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function loadSettings() {
      setLoading(true);
      setLoadError(null);

      try {
        const settings = await getWidgetSettings();
        if (!cancelled && settings) {
          setForm(settingsToFormState(settings));
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(
            getErrorMessage(error, "Unable to load website chat settings."),
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
  }, [reloadKey]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaveError(null);
    setSaveMessage(null);

    try {
      const saved = await updateWidgetSettings({
        project_id: form.projectId,
        display_name: form.displayName,
        welcome_message: form.welcomeMessage,
        position: form.position,
        enabled: form.enabled,
        allowed_domains: parseAllowedDomains(form.allowedDomains),
      });
      setForm(settingsToFormState(saved));
      setSaveMessage("Website chat settings saved.");
    } catch (error) {
      setSaveError(
        getErrorMessage(error, "Unable to save website chat settings."),
      );
    } finally {
      setSaving(false);
    }
  }

  async function copyInstallationSnippet() {
    const snippet = `<script src="${API_BASE_URL}/widget.js" data-project="${form.projectId}"></script>`;

    try {
      await navigator.clipboard.writeText(snippet);
      setCopyMessage("Installation snippet copied.");
    } catch {
      setCopyMessage("Copy is unavailable. Select the snippet manually.");
    }
  }

  if (loading) {
    return <LoadingState label="Loading website chat settings..." />;
  }

  if (loadError) {
    return (
      <ErrorState
        title="Website chat unavailable"
        description={loadError}
        action={
          <button
            type="button"
            onClick={() => setReloadKey((current) => current + 1)}
            className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900"
          >
            Try again
          </button>
        }
      />
    );
  }

  const previewAlignment =
    form.position === "bottom-left" ? "justify-start" : "justify-end";

  return (
    <div className="space-y-8">
      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6"
      >
        <div className="grid gap-6 lg:grid-cols-2">
          <label className="block text-sm text-zinc-300">
            <span>Project ID</span>
            <input
              value={form.projectId}
              readOnly
              className={`${inputClassName} cursor-not-allowed text-zinc-500`}
              maxLength={64}
              required
            />
            <span className="mt-2 block text-xs text-zinc-600">
              This workspace uses the fixed identifier shown in the
              installation script.
            </span>
          </label>

          <label className="block text-sm text-zinc-300">
            <span>Display name</span>
            <input
              value={form.displayName}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  displayName: event.target.value,
                }))
              }
              className={inputClassName}
              maxLength={255}
              required
            />
          </label>

          <label className="block text-sm text-zinc-300 lg:col-span-2">
            <span>Welcome message</span>
            <textarea
              value={form.welcomeMessage}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  welcomeMessage: event.target.value,
                }))
              }
              className={`${inputClassName} min-h-28 resize-y`}
              maxLength={2000}
              required
            />
          </label>

          <label className="block text-sm text-zinc-300">
            <span>Position</span>
            <select
              value={form.position}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  position: event.target.value as WidgetPosition,
                }))
              }
              className={inputClassName}
            >
              <option value="bottom-right">Bottom right</option>
              <option value="bottom-left">Bottom left</option>
            </select>
          </label>

          <label className="flex items-center gap-3 self-end rounded-lg border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  enabled: event.target.checked,
                }))
              }
              className="h-4 w-4 accent-white"
            />
            <span>
              <span className="block font-medium text-white">Enabled</span>
              <span className="mt-1 block text-xs text-zinc-600">
                Disabled widgets reject new public sessions.
              </span>
            </span>
          </label>

          <label className="block text-sm text-zinc-300 lg:col-span-2">
            <span>Allowed website origins</span>
            <textarea
              value={form.allowedDomains}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  allowedDomains: event.target.value,
                }))
              }
              className={`${inputClassName} min-h-32 resize-y font-mono text-xs`}
              placeholder="http://localhost:3002\nhttps://example.com"
              aria-describedby="allowed-origins-help"
            />
            <span
              id="allowed-origins-help"
              className="mt-2 block text-xs leading-5 text-zinc-600"
            >
              Enter one full HTTP(S) origin per line, including a non-default
              port when needed. Origins are matched exactly.
            </span>
          </label>
        </div>

        {saveError ? (
          <p role="alert" className="mt-5 text-sm text-red-300">
            {saveError}
          </p>
        ) : null}
        {saveMessage ? (
          <p role="status" className="mt-5 text-sm text-emerald-300">
            {saveMessage}
          </p>
        ) : null}

        <div className="mt-6 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-zinc-950 transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save settings"}
          </button>
        </div>
      </form>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              Installation
            </p>
            <h2 className="mt-2 text-lg font-semibold text-white">
              Add AgentDesk to your website
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
              Serve this script from the AgentDesk backend, then add the
              embedding site&apos;s exact origin above.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void copyInstallationSnippet()}
            className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900"
          >
            Copy snippet
          </button>
        </div>
        <code className="mt-5 block overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-xs leading-6 text-zinc-300">
          {`<script src="${API_BASE_URL}/widget.js" data-project="${form.projectId}"></script>`}
        </code>
        {copyMessage ? (
          <p role="status" className="mt-3 text-xs text-zinc-500">
            {copyMessage}
          </p>
        ) : null}
      </section>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
              Preview
            </p>
            <h2 className="mt-2 text-lg font-semibold text-white">
              Customer-facing launcher
            </h2>
          </div>
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
              form.enabled
                ? "border-emerald-900/70 bg-emerald-950/30 text-emerald-300"
                : "border-zinc-700 bg-zinc-900 text-zinc-500"
            }`}
          >
            {form.enabled ? "Enabled" : "Disabled"}
          </span>
        </div>

        <div className="mt-5 flex min-h-40 items-end rounded-lg border border-zinc-800 bg-zinc-950 p-5">
          <div className={`flex w-full ${previewAlignment}`}>
            <div className="rounded-full bg-zinc-100 px-4 py-2.5 text-sm font-semibold text-zinc-950 shadow-lg">
              Need help?
            </div>
          </div>
        </div>
        <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-950/50 p-4">
          <p className="text-sm font-medium text-zinc-200">
            {form.displayName}
          </p>
          <p className="mt-2 text-sm leading-6 text-zinc-500">
            {form.welcomeMessage}
          </p>
        </div>
      </section>
    </div>
  );
}
