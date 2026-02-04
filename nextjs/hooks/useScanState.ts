'use client';

import { useState, useCallback } from 'react';
import { ScanState } from '@/lib/types';
import { scanImage } from '@/lib/api-client';
import { getDisplayableImageUrl } from '@/lib/image-converter';
import { useScanCache } from './useScanCache';
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
      // Cache result for offline access
      if (featureFlags.offlineCache && imageUri) {
        scanCache.save(result.data, imageUri);
      }
      setState({ status: 'results', response: result.data, imageUri: imageUri || '' });
    } else {
      if (imageUri) URL.revokeObjectURL(imageUri);
      setState({ status: 'error', message: result.error.message });
    }
  }, [debugMode, scanCache]);

  const reset = useCallback(() => {
    if (state.status === 'results' && state.imageUri) {
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
