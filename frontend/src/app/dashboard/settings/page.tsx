"use client";

import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import PageHeader from "@/components/dashboard/page-header";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  getAISettings,
  getCompanySettings,
  testAIConnection,
  updateAISettings,
  updateCompanySettings,
  type CompanySettings,
} from "@/lib/api";
import {
  AI_MODEL_OPTIONS,
  AI_PROVIDER_OPTIONS,
  DEFAULT_AI_MODELS,
  getAIProviderOption,
  isAIProvider,
  type AIProviderId,
} from "@/lib/ai-providers";

const inputClassName =
  "mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm text-white outline-none transition-colors focus:border-zinc-500 disabled:cursor-not-allowed disabled:opacity-60";

type CompanyFormState = {
  name: string;
  website: string;
  industry: string;
  supportName: string;
  defaultLanguage: string;
  timezone: string;
};

const defaultCompanyForm: CompanyFormState = {
  name: "",
  website: "",
  industry: "",
  supportName: "",
  defaultLanguage: "en",
  timezone: "UTC",
};

function companyToFormState(company: CompanySettings): CompanyFormState {
  return {
    name: company.name,
    website: company.website ?? "",
    industry: company.industry ?? "",
    supportName: company.support_name ?? "",
    defaultLanguage: company.default_language,
    timezone: company.timezone,
  };
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function SettingsPage() {
  const apiKeyInputRef = useRef<HTMLInputElement>(null);

  const [company, setCompany] =
    useState<CompanyFormState>(defaultCompanyForm);
  const [provider, setProvider] = useState<AIProviderId>("gemini");
  const [model, setModel] = useState(DEFAULT_AI_MODELS.gemini);
  const [apiKey, setApiKey] = useState("");
  const [existingApiKey, setExistingApiKey] = useState(false);
  const [tested, setTested] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [companySaving, setCompanySaving] = useState(false);
  const [aiTesting, setAiTesting] = useState(false);
  const [aiSaving, setAiSaving] = useState(false);

  const [companyMessage, setCompanyMessage] = useState<string | null>(null);
  const [companyError, setCompanyError] = useState<string | null>(null);
  const [aiMessage, setAiMessage] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadSettings() {
      try {
        const [companySettings, aiSettings] = await Promise.all([
          getCompanySettings(),
          getAISettings(),
        ]);

        if (cancelled) {
          return;
        }

        if (companySettings) {
          setCompany(companyToFormState(companySettings));
        }

        if (aiSettings) {
          const nextProvider = isAIProvider(aiSettings.provider)
            ? aiSettings.provider
            : "gemini";

          setProvider(nextProvider);
          setModel(aiSettings.model || DEFAULT_AI_MODELS[nextProvider]);
          setExistingApiKey(aiSettings.api_key_configured);
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(
            getErrorMessage(error, "Unable to load workspace settings."),
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

  async function handleCompanySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCompanySaving(true);
    setCompanyError(null);
    setCompanyMessage(null);

    try {
      const savedCompany = await updateCompanySettings({
        name: company.name,
        website: company.website || null,
        industry: company.industry || null,
        support_name: company.supportName || null,
        default_language: company.defaultLanguage,
        timezone: company.timezone,
      });

      setCompany(companyToFormState(savedCompany));
      setCompanyMessage("Company settings saved.");
    } catch (error) {
      setCompanyError(
        getErrorMessage(error, "Unable to save company settings."),
      );
    } finally {
      setCompanySaving(false);
    }
  }

  async function handleTestAIConnection() {
    const normalizedApiKey = apiKey.trim();
    const providerOption = getAIProviderOption(provider);
    const keyLabel = providerOption?.keyLabel ?? "API key";

    if (!normalizedApiKey) {
      setAiError(`Enter a ${keyLabel} before testing.`);
      setAiMessage(null);
      return;
    }

    setAiTesting(true);
    setAiError(null);
    setAiMessage(null);
    setTested(false);

    try {
      const result = await testAIConnection({
        provider,
        model,
        api_key: normalizedApiKey,
      });

      if (result.success) {
        setTested(true);
        setAiMessage(result.message);
      } else {
        setAiError(result.message);
      }
    } catch (error) {
      setAiError(getErrorMessage(error, "Connection test failed."));
    } finally {
      setAiTesting(false);
    }
  }

  async function saveAISettings(allowUntested: boolean) {
    const normalizedApiKey = apiKey.trim();
    const keepingExistingKey = existingApiKey && !normalizedApiKey;
    const providerOption = getAIProviderOption(provider);
    const keyLabel = providerOption?.keyLabel ?? "API key";

    if (!normalizedApiKey && !keepingExistingKey) {
      setAiError(`Enter a ${keyLabel} before saving.`);
      setAiMessage(null);
      return;
    }

    if (normalizedApiKey && !tested && !allowUntested) {
      setAiError(
        "Test the connection first, or explicitly save without testing.",
      );
      setAiMessage(null);
      return;
    }

    setAiSaving(true);
    setAiError(null);
    setAiMessage(null);

    try {
      const savedSettings = await updateAISettings({
        provider,
        model,
        api_key: normalizedApiKey || undefined,
        embedding_provider: "local",
        embedding_model: null,
        enabled: true,
      });

      setModel(savedSettings.model);
      setExistingApiKey(savedSettings.api_key_configured);
      setApiKey("");
      setTested(false);
      setAiMessage("AI provider settings saved.");
    } catch (error) {
      setAiError(getErrorMessage(error, "Unable to save AI settings."));
    } finally {
      setAiSaving(false);
    }
  }

  function handleProviderChange(nextProvider: AIProviderId) {
    setProvider(nextProvider);
    setModel(DEFAULT_AI_MODELS[nextProvider]);
    setApiKey("");
    setExistingApiKey(false);
    setTested(false);
    setAiMessage(null);
    setAiError(null);
  }

  function handleAISubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void saveAISettings(false);
  }

  function focusReplacementKey() {
    setApiKey("");
    setTested(false);
    setAiMessage(null);
    apiKeyInputRef.current?.focus();
  }

  if (loading) {
    return (
      <div>
        <PageHeader
          eyebrow="Workspace"
          title="Settings"
          description="Manage the configuration used by AgentDesk."
        />
        <div className="mt-8">
          <LoadingState label="Loading workspace settings..." />
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div>
        <PageHeader
          eyebrow="Workspace"
          title="Settings"
          description="Manage the configuration used by AgentDesk."
        />
        <div className="mt-8">
          <ErrorState
            title="Settings unavailable"
            description={loadError}
            action={
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900"
              >
                Reload
              </button>
            }
          />
        </div>
      </div>
    );
  }

  const hasNewApiKey = apiKey.trim().length > 0;
  const formDisabled = companySaving || aiTesting || aiSaving;
  const providerOption = getAIProviderOption(provider);
  const apiKeyLabel = providerOption?.keyLabel ?? "API key";
  const modelOptions = AI_MODEL_OPTIONS[provider];

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="Manage the configuration used by AgentDesk without editing files."
      />

      <div className="mt-8 grid gap-6 xl:grid-cols-2">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <div>
            <h2 className="text-lg font-semibold text-white">Company</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">
              Update the company context used across the support workspace.
            </p>
          </div>

          <form onSubmit={handleCompanySubmit} className="mt-6 space-y-5">
            <div>
              <label htmlFor="settings-company-name" className="text-sm text-zinc-300">
                Company name <span className="text-amber-300">*</span>
              </label>
              <input
                id="settings-company-name"
                required
                value={company.name}
                autoComplete="organization"
                onChange={(event) =>
                  setCompany((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                className={inputClassName}
                disabled={formDisabled}
              />
            </div>

            <div>
              <label htmlFor="settings-company-website" className="text-sm text-zinc-300">
                Website
              </label>
              <input
                id="settings-company-website"
                type="url"
                value={company.website}
                autoComplete="url"
                onChange={(event) =>
                  setCompany((current) => ({
                    ...current,
                    website: event.target.value,
                  }))
                }
                className={inputClassName}
                placeholder="https://example.com"
                disabled={formDisabled}
              />
            </div>

            <div>
              <label htmlFor="settings-company-industry" className="text-sm text-zinc-300">
                Industry
              </label>
              <input
                id="settings-company-industry"
                value={company.industry}
                autoComplete="off"
                onChange={(event) =>
                  setCompany((current) => ({
                    ...current,
                    industry: event.target.value,
                  }))
                }
                className={inputClassName}
                disabled={formDisabled}
              />
            </div>

            <div>
              <label htmlFor="settings-support-name" className="text-sm text-zinc-300">
                Support name
              </label>
              <input
                id="settings-support-name"
                value={company.supportName}
                autoComplete="organization"
                onChange={(event) =>
                  setCompany((current) => ({
                    ...current,
                    supportName: event.target.value,
                  }))
                }
                className={inputClassName}
                disabled={formDisabled}
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="settings-language" className="text-sm text-zinc-300">
                  Default language
                </label>
                <input
                  id="settings-language"
                  value={company.defaultLanguage}
                  autoComplete="off"
                  onChange={(event) =>
                    setCompany((current) => ({
                      ...current,
                      defaultLanguage: event.target.value,
                    }))
                  }
                  className={inputClassName}
                  disabled={formDisabled}
                />
              </div>

              <div>
                <label htmlFor="settings-timezone" className="text-sm text-zinc-300">
                  Timezone
                </label>
                <input
                  id="settings-timezone"
                  value={company.timezone}
                  autoComplete="off"
                  onChange={(event) =>
                    setCompany((current) => ({
                      ...current,
                      timezone: event.target.value,
                    }))
                  }
                  className={inputClassName}
                  disabled={formDisabled}
                />
              </div>
            </div>

            {companyMessage && (
              <p
                role="status"
                className="rounded-lg border border-emerald-900 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300"
              >
                {companyMessage}
              </p>
            )}
            {companyError && (
              <p
                role="alert"
                className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
              >
                {companyError}
              </p>
            )}

            <button
              type="submit"
              disabled={formDisabled}
              className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-black transition-opacity disabled:opacity-50"
            >
              {companySaving ? "Saving..." : "Save company"}
            </button>
          </form>
        </section>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
          <div>
            <h2 className="text-lg font-semibold text-white">AI Provider</h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">
              {providerOption?.description ??
                "Configure the provider used for support automation. API keys are encrypted server-side."}
            </p>
          </div>

          <form onSubmit={handleAISubmit} className="mt-6 space-y-5">
            <div>
              <label
                htmlFor="settings-provider"
                className="text-sm text-zinc-300"
              >
                Provider
              </label>
              <select
                id="settings-provider"
                name="provider"
                value={provider}
                onChange={(event) => {
                  if (isAIProvider(event.target.value)) {
                    handleProviderChange(event.target.value);
                  }
                }}
                className={inputClassName}
                disabled={formDisabled}
              >
                {AI_PROVIDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="settings-model" className="text-sm text-zinc-300">
                Model
              </label>
              <input
                id="settings-model"
                name="model"
                value={model}
                list="settings-ai-model-options"
                onChange={(event) => {
                  setModel(event.target.value);
                  setTested(false);
                  setAiMessage(null);
                }}
                className={inputClassName}
                disabled={formDisabled}
              />
              <datalist id="settings-ai-model-options">
                {modelOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </datalist>
              {provider === "openrouter" && (
                <p className="mt-2 text-xs leading-5 text-zinc-500">
                  Enter any OpenRouter author/model slug. The selected model
                  must support structured output.
                </p>
              )}
            </div>

            <div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label htmlFor="settings-api-key" className="text-sm text-zinc-300">
                  {apiKeyLabel}
                </label>
                <span className="text-xs text-zinc-500">
                  API key: {existingApiKey ? "Configured" : "Not configured"}
                </span>
              </div>
              <input
                ref={apiKeyInputRef}
                id="settings-api-key"
                type="password"
                value={apiKey}
                autoComplete="new-password"
                spellCheck={false}
                onChange={(event) => {
                  setApiKey(event.target.value);
                  setTested(false);
                  setAiMessage(null);
                }}
                placeholder={
                  existingApiKey
                    ? "Enter a replacement API key"
                    : `Enter ${apiKeyLabel}`
                }
                className={inputClassName}
                disabled={formDisabled}
              />
              <p className="mt-2 text-xs leading-5 text-zinc-600">
                Leave this field empty to keep the existing key. The key is never returned by AgentDesk.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => void handleTestAIConnection()}
                disabled={formDisabled || !hasNewApiKey}
                className="rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-200 transition-colors hover:border-zinc-500 hover:bg-zinc-900 disabled:opacity-50"
              >
                {aiTesting ? "Testing..." : "Test connection"}
              </button>
              {existingApiKey && (
                <button
                  type="button"
                  onClick={focusReplacementKey}
                  disabled={formDisabled}
                  className="rounded-lg border border-zinc-800 px-4 py-2.5 text-sm text-zinc-400 transition-colors hover:border-zinc-600 hover:text-zinc-200 disabled:opacity-50"
                >
                  Replace API key
                </button>
              )}
            </div>

            {aiMessage && (
              <p
                role="status"
                className="rounded-lg border border-emerald-900 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-300"
              >
                {aiMessage}
              </p>
            )}
            {aiError && (
              <p
                role="alert"
                className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300"
              >
                {aiError}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-3">
              {hasNewApiKey && !tested && (
                <button
                  type="button"
                  onClick={() => void saveAISettings(true)}
                  disabled={formDisabled}
                  className="rounded-lg border border-zinc-700 px-4 py-2.5 text-sm text-zinc-300 transition-colors hover:border-zinc-500 hover:bg-zinc-900 disabled:opacity-50"
                >
                  Save without testing
                </button>
              )}
              <button
                type="submit"
                disabled={formDisabled}
                className="rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-black transition-opacity disabled:opacity-50"
              >
                {aiSaving ? "Saving..." : "Save AI settings"}
              </button>
            </div>
          </form>
        </section>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6 xl:col-span-2">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Storage</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-500">
                AgentDesk currently stores application data in a local SQLite database on this machine.
              </p>
            </div>
            <span className="rounded-full border border-emerald-900 bg-emerald-950/30 px-3 py-1 text-xs font-medium text-emerald-300">
              Ready
            </span>
          </div>

          <div className="mt-6 flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-950/60 p-4">
            <input
              id="settings-storage-sqlite"
              type="radio"
              checked
              readOnly
              aria-label="Local SQLite storage"
              className="mt-1"
            />
            <div>
              <label htmlFor="settings-storage-sqlite" className="text-sm font-medium text-zinc-200">
                Local SQLite
              </label>
              <p className="mt-1 text-sm text-zinc-500">
                This is the only supported storage option in the current release.
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
