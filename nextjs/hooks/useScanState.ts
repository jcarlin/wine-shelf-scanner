'use client';

import { useState, useCallback } from 'react';
import { ScanState } from '@/lib/types';
import { scanImage } from '@/lib/api-client';

export function useScanState() {
  const [state, setState] = useState<ScanState>({ status: 'idle' });
  const [debugMode, setDebugMode] = useState(false);

  const processImage = useCallback(async (file: File) => {
    setState({ status: 'processing' });

    // Create object URL for display
    const imageUri = URL.createObjectURL(file);

    const result = await scanImage(file, { debug: debugMode });

    if (result.success) {
      setState({ status: 'results', response: result.data, imageUri });
    } else {
      URL.revokeObjectURL(imageUri);
      setState({ status: 'error', message: result.error.message });
    }
  }, [debugMode]);

  const reset = useCallback(() => {
    if (state.status === 'results') {
      URL.revokeObjectURL(state.imageUri);
    }
    setState({ status: 'idle' });
  }, [state]);

  const toggleDebugMode = useCallback(() => {
    setDebugMode((prev) => !prev);
  }, []);

  return { state, processImage, reset, debugMode, toggleDebugMode };
}
