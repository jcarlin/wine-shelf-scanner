'use client';

import { useState, useCallback, useRef } from 'react';
import { ScanState, ScanResponse, WineResult } from '@/lib/types';
import { scanImageStream } from '@/lib/api-client';
import { getDisplayableImageUrl } from '@/lib/image-converter';
import { useScanCache } from './useScanCache';
import { featureFlags } from '@/lib/feature-flags';
import { Config } from '@/lib/config';

export function useScanState() {
  const [state, setState] = useState<ScanState>({ status: 'idle' });
  const [debugMode, setDebugMode] = useState(Config.DEBUG_MODE);
  const scanCache = useScanCache();
  const lockedRatingsRef = useRef<Map<string, number>>(new Map());

  const processImage = useCallback(async (file: File) => {
    let imageUri: string | null = null;

    // Create displayable URL - converts HEIC to JPEG if needed
    try {
      imageUri = await getDisplayableImageUrl(file);
    } catch (err) {
      console.warn('Could not create preview (HEIC conversion failed), continuing with scan:', err);
    }

    setState({ status: 'processing', imageUri });
    lockedRatingsRef.current = new Map();

    const resolvedImageUri = imageUri || '';

    await scanImageStream(
      file,
      {
        onPhase1: (data) => {
          // Lock ratings from phase1
          for (const w of data.results) {
            if (w.rating !== null) {
              lockedRatingsRef.current.set(w.wine_name.toLowerCase().trim(), w.rating);
            }
          }
          setState({ status: 'partial_results', response: data, imageUri: resolvedImageUri });
        },
        onPhase2: (data) => {
          // Enforce immutability: restore locked ratings, then lock new ones
          const merged = data.results.map(w => {
            const key = w.wine_name.toLowerCase().trim();
            const locked = lockedRatingsRef.current.get(key);
            return locked !== undefined ? { ...w, rating: locked } : w;
          });

          // Lock any new ratings from phase2
          for (const w of merged) {
            const key = w.wine_name.toLowerCase().trim();
            if (w.rating !== null && !lockedRatingsRef.current.has(key)) {
              lockedRatingsRef.current.set(key, w.rating!);
            }
          }

          const mergedData = { ...data, results: merged };
          if (featureFlags.offlineCache && resolvedImageUri) {
            scanCache.save(mergedData, resolvedImageUri);
          }
          setState({ status: 'results', response: mergedData, imageUri: resolvedImageUri });
        },
        onMetadata: (metadata) => {
          // Enrich existing wine results with metadata without changing ratings
          setState((prev) => {
            if (prev.status !== 'results' && prev.status !== 'partial_results') return prev;
            const enrichedResults = prev.response.results.map((w: WineResult) => {
              const meta = metadata[w.wine_name];
              if (!meta) return w;
              return {
                ...w,
                wine_type: (meta.wine_type as string) ?? w.wine_type,
                brand: (meta.brand as string) ?? w.brand,
                region: (meta.region as string) ?? w.region,
                varietal: (meta.varietal as string) ?? w.varietal,
                blurb: (meta.blurb as string) ?? w.blurb,
                review_count: (meta.review_count as number) ?? w.review_count,
                review_snippets: (meta.review_snippets as string[]) ?? w.review_snippets,
                wine_id: (meta.wine_id as number) ?? w.wine_id,
                pairing: (meta.pairing as string) ?? w.pairing,
                is_safe_pick: (meta.is_safe_pick as boolean) ?? w.is_safe_pick,
              };
            });
            return {
              ...prev,
              response: { ...prev.response, results: enrichedResults },
            };
          });
        },
        onError: (error) => {
          if (imageUri) URL.revokeObjectURL(imageUri);
          setState({ status: 'error', message: error.message });
        },
      },
      { debug: debugMode }
    );
  }, [debugMode, scanCache]);

  const reset = useCallback(() => {
    if (
      (state.status === 'results' || state.status === 'partial_results') &&
      state.imageUri
    ) {
      URL.revokeObjectURL(state.imageUri);
    } else if (state.status === 'processing' && state.imageUri) {
      URL.revokeObjectURL(state.imageUri);
    }
    lockedRatingsRef.current = new Map();
    setState({ status: 'idle' });
  }, [state]);

  const toggleDebugMode = useCallback(() => {
    setDebugMode((prev) => !prev);
  }, []);

  return { state, processImage, reset, debugMode, toggleDebugMode, scanCache };
}
