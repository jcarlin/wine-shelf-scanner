/**
 * Shelf ranking utilities for wine display.
 *
 * Centralizes the logic for computing shelf rankings to avoid
 * duplication between OverlayContainer.tsx and ResultsView.tsx.
 */

import { WineResult } from './types';
import { isVisible } from './overlay-math';

/** Minimum number of visible wines required to show shelf rankings */
export const MINIMUM_RANKED_WINES = 3;

/** Number of top wines to emphasize */
export const TOP_WINES_COUNT = 3;

export interface ShelfRank {
  rank: number;
  total: number;
}

/**
 * Compute shelf rankings for wines based on rating.
 *
 * Wines with equal ratings receive the same rank (dense ranking).
 * Returns empty map if fewer than MINIMUM_RANKED_WINES visible wines have ratings.
 *
 * @param wines - Array of wine results
 * @returns Map of wine name to rank info
 */
export function computeShelfRankings(wines: WineResult[]): Map<string, ShelfRank> {
  const visibleWines = wines.filter((w) => isVisible(w.confidence));
  const ranked = [...visibleWines]
    .filter((w) => w.rating !== null)
    .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));

  if (ranked.length < MINIMUM_RANKED_WINES) {
    return new Map();
  }

  const rankings = new Map<string, ShelfRank>();
  let currentRank = 1;

  ranked.forEach((wine, index) => {
    // Same rating = same rank (dense ranking)
    if (index > 0 && wine.rating !== ranked[index - 1].rating) {
      currentRank = index + 1;
    }
    rankings.set(wine.wine_name, { rank: currentRank, total: ranked.length });
  });

  return rankings;
}

/**
 * Get the names of the top N wines by rating.
 *
 * @param wines - Array of wine results
 * @param count - Number of top wines to return (default: TOP_WINES_COUNT)
 * @returns Array of wine names
 */
export function getTopWineNames(wines: WineResult[], count: number = TOP_WINES_COUNT): string[] {
  return [...wines]
    .filter((w) => isVisible(w.confidence) && w.rating !== null)
    .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
    .slice(0, count)
    .map((w) => w.wine_name);
}
