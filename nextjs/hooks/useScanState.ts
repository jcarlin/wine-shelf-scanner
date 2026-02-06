'use client';

import { useState, useCallback } from 'react';
import { ScanState } from '@/lib/types';
import { scanImage } from '@/lib/api-client';
import { getDisplayableImageUrl } from '@/lib/image-converter';
import { useScanCache, toBase64DataUri } from './useScanCache';
import { featureFlags } from '@/lib/feature-flags';

export function useScanState() {
  const [state, setState] = useState<ScanState>({ status: 'idle' });
  const [debugMode, setDebugMode] = useState(false);
  const scanCache = useScanCache();

  const processImage = useCallback(async (file: File) => {
    let imageUri: string | null = null;

    // Create displayable URL - converts HEIC to JPEG if needed
    // If conversion fails (unsupported HEIC variant), we continue without preview
    try {
      imageUri = await getDisplayableImageUrl(file);
    } catch (err) {
      console.warn('Could not create preview (HEIC conversion failed), continuing with scan:', err);
    }

    // Set processing state - imageUri may be null if HEIC conversion failed
    setState({ status: 'processing', imageUri });

    const result = await scanImage(file, { debug: debugMode });

    if (result.success) {
      // Cache result for offline access — convert blob URL to base64 for persistence
      if (featureFlags.offlineCache && imageUri) {
        try {
          const persistentUri = await toBase64DataUri(imageUri);
          scanCache.save(result.data, persistentUri);
        } catch {
          // Cache save failed (e.g., storage full) — non-blocking
        }
      }
      setState({ status: 'results', response: result.data, imageUri: imageUri || '' });
    } else {
      // On network error, fall back to cached scan if available (parity with iOS)
      if (
        featureFlags.offlineCache &&
        (result.error.type === 'NETWORK_ERROR' || result.error.type === 'TIMEOUT') &&
        scanCache.hasCachedScans()
      ) {
        const cached = scanCache.loadAll();
        if (cached.length > 0) {
          const mostRecent = cached[0];
          if (imageUri) URL.revokeObjectURL(imageUri);
          setState({
            status: 'cachedResults',
            response: mostRecent.response,
            imageUri: mostRecent.imageUri,
            timestamp: mostRecent.timestamp,
          });
          return;
        }
      }

      if (imageUri) URL.revokeObjectURL(imageUri);
      setState({ status: 'error', message: result.error.message });
    }
  }, [debugMode, scanCache]);

  const showCachedScan = useCallback((index: number) => {
    const cached = scanCache.loadAll();
    if (index >= 0 && index < cached.length) {
      const entry = cached[index];
      setState({
        status: 'cachedResults',
        response: entry.response,
        imageUri: entry.imageUri,
        timestamp: entry.timestamp,
      });
    }
  }, [scanCache]);

  const reset = useCallback(() => {
    if (state.status === 'results' && state.imageUri) {
      // Only revoke blob URLs, not data URIs
      if (state.imageUri.startsWith('blob:')) {
        URL.revokeObjectURL(state.imageUri);
      }
    } else if (state.status === 'processing' && state.imageUri) {
      if (state.imageUri.startsWith('blob:')) {
        URL.revokeObjectURL(state.imageUri);
      }
    }
    setState({ status: 'idle' });
  }, [state]);

  const toggleDebugMode = useCallback(() => {
    setDebugMode((prev) => !prev);
  }, []);

  return { state, processImage, reset, debugMode, toggleDebugMode, scanCache, showCachedScan };
}
