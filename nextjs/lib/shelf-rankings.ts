/**
 * Shelf ranking utilities for wine display.
 *
 * Centralizes the logic for computing shelf rankings to avoid
 * duplication between OverlayContainer.tsx and ResultsView.tsx.
 */

import { WineResult } from './types';
import { isVisible } from './overlay-math';

/**
 * Rating descending, ties broken by confidence then name so ordering is
 * deterministic and exactly one wine can hold rank 1 (a rating tie was
 * rendering multiple BEST PICK tags).
 */
function byRatingThenConfidence(a: WineResult, b: WineResult): number {
  const ratingDiff = (b.rating ?? 0) - (a.rating ?? 0);
  if (ratingDiff !== 0) return ratingDiff;
  const confDiff = b.confidence - a.confidence;
  if (confDiff !== 0) return confDiff;
  return a.wine_name.localeCompare(b.wine_name);
}

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
    .sort(byRatingThenConfidence);

  if (ranked.length < MINIMUM_RANKED_WINES) {
    return new Map();
  }

  const rankings = new Map<string, ShelfRank>();
  ranked.forEach((wine, index) => {
    rankings.set(wine.wine_name, { rank: index + 1, total: ranked.length });
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
    .sort(byRatingThenConfidence)
    .slice(0, count)
    .map((w) => w.wine_name);
}
