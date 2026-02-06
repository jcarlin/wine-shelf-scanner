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

function envBool(key: string, defaultValue = true): boolean {
  const val = process.env[key];
  if (val === undefined) return defaultValue;
  return val.toLowerCase() === 'true';
}

export const featureFlags: FeatureFlagValues = {
  wineMemory: envBool('NEXT_PUBLIC_FEATURE_WINE_MEMORY'),
  shelfRanking: envBool('NEXT_PUBLIC_FEATURE_SHELF_RANKING'),
  safePick: envBool('NEXT_PUBLIC_FEATURE_SAFE_PICK'),
  pairings: envBool('NEXT_PUBLIC_FEATURE_PAIRINGS'),
  trustSignals: envBool('NEXT_PUBLIC_FEATURE_TRUST_SIGNALS', false),
  visualEmphasis: envBool('NEXT_PUBLIC_FEATURE_VISUAL_EMPHASIS'),
  cornerBrackets: envBool('NEXT_PUBLIC_FEATURE_CORNER_BRACKETS', false),
  offlineCache: envBool('NEXT_PUBLIC_FEATURE_OFFLINE_CACHE'),
  share: envBool('NEXT_PUBLIC_FEATURE_SHARE'),
  bugReport: envBool('NEXT_PUBLIC_FEATURE_BUG_REPORT'),
};

export function useFeatureFlags(): FeatureFlagValues {
  return featureFlags;
}
