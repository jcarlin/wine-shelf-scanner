import React, { createContext, useContext, useMemo } from 'react';
import Constants from 'expo-constants';

export interface FeatureFlagValues {
  wineMemory: boolean;
  shelfRanking: boolean;
  safePick: boolean;
  pairings: boolean;
}

const defaults: FeatureFlagValues = {
  wineMemory: Constants.expoConfig?.extra?.featureWineMemory ?? false,
  shelfRanking: Constants.expoConfig?.extra?.featureShelfRanking ?? false,
  safePick: Constants.expoConfig?.extra?.featureSafePick ?? false,
  pairings: Constants.expoConfig?.extra?.featurePairings ?? false,
};

const FeatureFlagContext = createContext<FeatureFlagValues>(defaults);

export function FeatureFlagProvider({ children }: { children: React.ReactNode }) {
  const flags = useMemo(() => defaults, []);
  return (
    <FeatureFlagContext.Provider value={flags}>
      {children}
    </FeatureFlagContext.Provider>
  );
}

export function useFeatureFlags(): FeatureFlagValues {
  return useContext(FeatureFlagContext);
}
