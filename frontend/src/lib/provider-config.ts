import type { UserFacingProvider } from "../types/research";

const ALL_PROVIDERS: readonly UserFacingProvider[] = ["qwen", "claude"];

export function parseEnabledProviders(value: string | undefined): readonly UserFacingProvider[] {
  if (value === undefined || value.trim() === "") {
    return ALL_PROVIDERS;
  }

  const providers = value
    .split(",")
    .map((provider) => provider.trim().toLowerCase())
    .filter((provider): provider is UserFacingProvider =>
      ALL_PROVIDERS.includes(provider as UserFacingProvider),
    )
    .filter((provider, index, configured) => configured.indexOf(provider) === index);

  if (providers.length === 0) {
    throw new Error("VITE_ENABLED_LLM_PROVIDERS must include qwen or claude.");
  }

  return providers;
}

export const enabledProviders = parseEnabledProviders(import.meta.env.VITE_ENABLED_LLM_PROVIDERS);
export const defaultProvider = enabledProviders[0] ?? "claude";
