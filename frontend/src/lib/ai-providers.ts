export type AIProviderId = "gemini" | "openrouter";

export type AIProviderOption = {
  value: AIProviderId;
  label: string;
  keyLabel: string;
  description: string;
};

export type AIModelOption = {
  value: string;
  label: string;
};

export const AI_PROVIDER_OPTIONS: readonly AIProviderOption[] = [
  {
    value: "gemini",
    label: "Google Gemini",
    keyLabel: "Gemini API key",
    description: "Configure Google Gemini for AgentDesk.",
  },
  {
    value: "openrouter",
    label: "OpenRouter",
    keyLabel: "OpenRouter API key",
    description: "Route AgentDesk generation through OpenRouter.",
  },
];

export const AI_MODEL_OPTIONS: Record<AIProviderId, readonly AIModelOption[]> = {
  gemini: [
    {
      value: "gemini-3.6-flash",
      label: "Gemini 3.6 Flash",
    },
    {
      value: "gemini-2.5-flash",
      label: "Gemini 2.5 Flash",
    },
    {
      value: "gemini-2.5-pro",
      label: "Gemini 2.5 Pro",
    },
  ],
  openrouter: [
    {
      value: "google/gemma-4-26b-a4b-it",
      label: "Google Gemma 4 26B (example)",
    },
    {
      value: "openrouter/free",
      label: "OpenRouter Free (example)",
    },
  ],
};

export const DEFAULT_AI_MODELS: Record<AIProviderId, string> = {
  gemini: "gemini-3.6-flash",
  openrouter: "google/gemma-4-26b-a4b-it",
};

export function isAIProvider(
  value: string | null | undefined,
): value is AIProviderId {
  return value === "gemini" || value === "openrouter";
}

export function getAIProviderOption(
  provider: string | null | undefined,
): AIProviderOption | null {
  if (!isAIProvider(provider)) {
    return null;
  }

  return AI_PROVIDER_OPTIONS.find((option) => option.value === provider) ?? null;
}

export function getAIProviderLabel(
  provider: string | null | undefined,
): string {
  return getAIProviderOption(provider)?.label ?? provider ?? "AI provider";
}
