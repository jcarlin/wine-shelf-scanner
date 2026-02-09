export interface FeatureFlagValues {
  wineMemory: boolean;
  shelfRanking: boolean;
  safePick: boolean;
  pairings: boolean;
  trustSignals: boolean;
  visualEmphasis: boolean;
  cornerBrackets: boolean;
  offlineCache: boolean;
  share: boolean;
  bugReport: boolean;
}

function toBool(val: string | undefined, defaultValue: boolean): boolean {
  if (val === undefined) return defaultValue;
  return val.toLowerCase() === 'true';
}

// Each flag uses a literal process.env.NEXT_PUBLIC_* access so Next.js can
// statically replace the value at build time. Dynamic key access
// (process.env[key]) is NOT inlined and always returns undefined on the client.
export const featureFlags: FeatureFlagValues = {
  wineMemory: toBool(process.env.NEXT_PUBLIC_FEATURE_WINE_MEMORY, true),
  shelfRanking: toBool(process.env.NEXT_PUBLIC_FEATURE_SHELF_RANKING, true),
  safePick: toBool(process.env.NEXT_PUBLIC_FEATURE_SAFE_PICK, true),
  pairings: toBool(process.env.NEXT_PUBLIC_FEATURE_PAIRINGS, true),
  trustSignals: toBool(process.env.NEXT_PUBLIC_FEATURE_TRUST_SIGNALS, false),
  visualEmphasis: toBool(process.env.NEXT_PUBLIC_FEATURE_VISUAL_EMPHASIS, true),
  cornerBrackets: toBool(process.env.NEXT_PUBLIC_FEATURE_CORNER_BRACKETS, false),
  offlineCache: toBool(process.env.NEXT_PUBLIC_FEATURE_OFFLINE_CACHE, true),
  share: toBool(process.env.NEXT_PUBLIC_FEATURE_SHARE, true),
  bugReport: toBool(process.env.NEXT_PUBLIC_FEATURE_BUG_REPORT, true),
};

export function useFeatureFlags(): FeatureFlagValues {
  return featureFlags;
}
