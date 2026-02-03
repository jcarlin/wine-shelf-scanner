'use client';

import { useState, useCallback } from 'react';
import { ScanState } from '@/lib/types';
import { scanImage } from '@/lib/api-client';
import { getDisplayableImageUrl } from '@/lib/image-converter';

export function useScanState() {
  const [state, setState] = useState<ScanState>({ status: 'idle' });
  const [debugMode, setDebugMode] = useState(false);

  const processImage = useCallback(async (file: File) => {
    // Create displayable URL first - converts HEIC to JPEG if needed
    const imageUri = await getDisplayableImageUrl(file);

    // Set processing state WITH the image URI so we can show it
    setState({ status: 'processing', imageUri });

    const result = await scanImage(file, { debug: debugMode });

    if (result.success) {
      setState({ status: 'results', response: result.data, imageUri });
    } else {
      URL.revokeObjectURL(imageUri);
      setState({ status: 'error', message: result.error.message });
    }
  }, [debugMode]);

  const reset = useCallback(() => {
    if (state.status === 'results' || state.status === 'processing') {
      URL.revokeObjectURL(state.imageUri);
    }
    setState({ status: 'idle' });
  }, [state]);

  const toggleDebugMode = useCallback(() => {
    setDebugMode((prev) => !prev);
  }, []);

  return { state, processImage, reset, debugMode, toggleDebugMode };
}
