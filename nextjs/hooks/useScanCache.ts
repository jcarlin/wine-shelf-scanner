'use client';

import { useCallback } from 'react';
import { ScanResponse } from '@/lib/types';

const CACHE_KEY = 'scan_cache_entries';
const MAX_ENTRIES = 10;

export interface CachedScan {
  response: ScanResponse;
  imageUri: string;
  timestamp: string; // ISO 8601
}

/**
 * Hook for caching scan results in localStorage for offline access.
 * Stores up to MAX_ENTRIES recent scans.
 */
export function useScanCache() {
  const save = useCallback((response: ScanResponse, imageUri: string) => {
    try {
      const entries = loadEntries();
      const entry: CachedScan = {
        response,
        imageUri,
        timestamp: new Date().toISOString(),
      };
      entries.unshift(entry);

      // Evict oldest if over limit
      while (entries.length > MAX_ENTRIES) {
        entries.pop();
      }

      localStorage.setItem(CACHE_KEY, JSON.stringify(entries));
    } catch {
      // localStorage may be full or unavailable
    }
  }, []);

  const loadAll = useCallback((): CachedScan[] => {
    return loadEntries();
  }, []);

  const hasCachedScans = useCallback((): boolean => {
    return loadEntries().length > 0;
  }, []);

  const clearAll = useCallback(() => {
    localStorage.removeItem(CACHE_KEY);
  }, []);

  return { save, loadAll, hasCachedScans, clearAll };
}

function loadEntries(): CachedScan[] {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as CachedScan[];
  } catch {
    return [];
  }
}
