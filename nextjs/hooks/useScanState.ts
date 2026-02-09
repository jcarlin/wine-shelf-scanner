'use client';

import { useState, useCallback } from 'react';
import { ScanState } from '@/lib/types';
import { scanImageStream } from '@/lib/api-client';
import { getDisplayableImageUrl } from '@/lib/image-converter';
import { useScanCache } from './useScanCache';
import { featureFlags } from '@/lib/feature-flags';
import { Config } from '@/lib/config';

export function useScanState() {
  const [state, setState] = useState<ScanState>({ status: 'idle' });
  const [debugMode, setDebugMode] = useState(Config.DEBUG_MODE);
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

    const resolvedImageUri = imageUri || '';

    await scanImageStream(
      file,
      {
        onPhase1: (_data) => {
          // Store for fallback if Gemini fails, but don't render yet.
          // The backend re-emits phase1 as phase2 if Gemini fails, so
          // the user will still see results — just from the phase2 callback.
        },
        onPhase2: (data) => {
          // Replace with Gemini-enhanced results
          if (featureFlags.offlineCache && resolvedImageUri) {
            scanCache.save(data, resolvedImageUri);
          }
          setState({ status: 'results', response: data, imageUri: resolvedImageUri });
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
      state.status === 'results' &&
      state.imageUri
    ) {
      URL.revokeObjectURL(state.imageUri);
    } else if (state.status === 'processing' && state.imageUri) {
      URL.revokeObjectURL(state.imageUri);
    }
    setState({ status: 'idle' });
  }, [state]);

  const toggleDebugMode = useCallback(() => {
    setDebugMode((prev) => !prev);
  }, []);

  return { state, processImage, reset, debugMode, toggleDebugMode, scanCache };
}
