export interface FeatureFlagValues {
  wineMemory: boolean;
  shelfRanking: boolean;
  safePick: boolean;
  pairings: boolean;
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
};

export function useFeatureFlags(): FeatureFlagValues {
  return featureFlags;
}
