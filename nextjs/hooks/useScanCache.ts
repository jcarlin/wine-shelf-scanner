'use client';

import { useCallback } from 'react';
import { ScanResponse } from '@/lib/types';

const CACHE_KEY = 'scan_cache_entries';
const MAX_ENTRIES = 10;

export interface CachedScan {
  response: ScanResponse;
  imageUri: string; // base64 data URI (persists across page refreshes)
  timestamp: string; // ISO 8601
}

/**
 * Hook for caching scan results in localStorage for offline access.
 * Stores up to MAX_ENTRIES recent scans.
 *
 * Images are stored as base64 data URIs so they survive page refreshes
 * (unlike blob URLs which are session-scoped).
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
      // localStorage may be full or unavailable — try evicting more
      try {
        const entries = loadEntries();
        // Keep only the 3 most recent to free space
        const trimmed = entries.slice(0, 3);
        localStorage.setItem(CACHE_KEY, JSON.stringify(trimmed));
      } catch {
        // Truly out of space or unavailable
      }
    }
  }, []);

  const loadAll = useCallback((): CachedScan[] => {
    return loadEntries();
  }, []);

  const hasCachedScans = useCallback((): boolean => {
    return loadEntries().length > 0;
  }, []);

  const clearAll = useCallback(() => {
    try {
      localStorage.removeItem(CACHE_KEY);
    } catch {
      // ignore
    }
  }, []);

  const deleteAt = useCallback((index: number) => {
    try {
      const entries = loadEntries();
      if (index >= 0 && index < entries.length) {
        entries.splice(index, 1);
        localStorage.setItem(CACHE_KEY, JSON.stringify(entries));
      }
    } catch {
      // ignore
    }
  }, []);

  return { save, loadAll, hasCachedScans, clearAll, deleteAt };
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

/**
 * Convert a blob URL or File to a base64 data URI for persistent storage.
 * Should be called before saving to cache.
 */
export async function toBase64DataUri(source: string | File): Promise<string> {
  // Already a data URI
  if (typeof source === 'string' && source.startsWith('data:')) {
    return source;
  }

  let blob: Blob;
  if (source instanceof File) {
    blob = source;
  } else {
    // Fetch blob URL to get actual data
    const response = await fetch(source);
    blob = await response.blob();
  }

  // Resize to reduce storage footprint (max 800px wide, JPEG quality 0.6)
  const resized = await resizeBlob(blob, 800, 0.6);

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(resized);
  });
}

/**
 * Resize an image blob to fit within maxWidth, re-encoded as JPEG.
 */
async function resizeBlob(
  blob: Blob,
  maxWidth: number,
  quality: number
): Promise<Blob> {
  const bitmap = await createImageBitmap(blob);
  const scale = bitmap.width > maxWidth ? maxWidth / bitmap.width : 1;
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);

  const canvas = new OffscreenCanvas(width, height);
  const ctx = canvas.getContext('2d');
  if (!ctx) return blob;

  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  return canvas.convertToBlob({ type: 'image/jpeg', quality });
}
