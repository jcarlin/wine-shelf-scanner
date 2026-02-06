'use client';

import { useState, useEffect, useRef } from 'react';
import { WineResult, ReviewItem } from '@/lib/types';
import { fetchWineReviews } from '@/lib/api-client';

/**
 * Prefetches reviews for all wines with a wine_id as soon as scan results arrive.
 *
 * Fires async fetches in parallel for each DB-matched wine. Returns a map of
 * wine_id -> ReviewItem[] that is populated as responses arrive.
 *
 * @param results - Wine results from the scan response
 * @returns Map of wine_id to review items (empty map until fetches complete)
 */
export function useWineReviews(results: WineResult[]): Map<number, ReviewItem[]> {
  const [reviewsMap, setReviewsMap] = useState<Map<number, ReviewItem[]>>(new Map());
  const fetchedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    // Find wines with wine_id that haven't been fetched yet
    const toFetch = results.filter(
      (w) => w.wine_id != null && !fetchedRef.current.has(w.wine_id)
    );

    if (toFetch.length === 0) return;

    // Mark as being fetched to prevent duplicates
    for (const w of toFetch) {
      fetchedRef.current.add(w.wine_id!);
    }

    // Fire all review fetches in parallel
    for (const wine of toFetch) {
      fetchWineReviews(wine.wine_id!, { limit: 5, textOnly: true }).then(
        (response) => {
          if (response && response.reviews.length > 0) {
            setReviewsMap((prev) => {
              const next = new Map(prev);
              next.set(wine.wine_id!, response.reviews);
              return next;
            });
          }
        }
      );
    }
  }, [results]);

  return reviewsMap;
}
