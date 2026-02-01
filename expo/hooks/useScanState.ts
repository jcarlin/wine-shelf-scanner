/**
 * Hook for managing scan state machine
 */

import { useState, useCallback } from 'react';
import * as ImagePicker from 'expo-image-picker';
import { ScanState, ScanResponse } from '../lib/types';
import { scanImage } from '../lib/api-client';
import { Config } from '../lib/config';

export interface UseScanStateReturn {
  state: ScanState;
  pickAndScan: () => Promise<void>;
  pickFromLibrary: () => Promise<void>;
  reset: () => void;
  debugMode: boolean;
  toggleDebugMode: () => void;
}

/**
 * Manages the scan state machine for wine shelf scanning
 *
 * States:
 * - idle: Ready to scan
 * - processing: Scanning in progress
 * - results: Scan completed with results
 * - error: Scan failed with error message
 */
export function useScanState(): UseScanStateReturn {
  const [state, setState] = useState<ScanState>({ status: 'idle' });
  const [debugMode, setDebugMode] = useState(true);

  /**
   * Toggle debug mode on/off
   */
  const toggleDebugMode = useCallback((): void => {
    setDebugMode((prev) => !prev);
  }, []);

  /**
   * Process an image URI through the scan API
   */
  const processImage = useCallback(async (imageUri: string): Promise<void> => {
    setState({ status: 'processing' });

    const result = await scanImage(imageUri, { debug: debugMode });

    if (result.success) {
      setState({
        status: 'results',
        response: result.data,
        imageUri,
      });
    } else {
      setState({
        status: 'error',
        message: result.error.message,
      });
    }
  }, [debugMode]);

  /**
   * Launch camera to capture and scan an image
   */
  const pickAndScan = useCallback(async (): Promise<void> => {
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: Config.IMAGE_QUALITY,
    });

    if (result.canceled || !result.assets?.[0]?.uri) {
      return;
    }

    await processImage(result.assets[0].uri);
  }, [processImage]);

  /**
   * Launch image library to select and scan an image
   */
  const pickFromLibrary = useCallback(async (): Promise<void> => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: Config.IMAGE_QUALITY,
    });

    if (result.canceled || !result.assets?.[0]?.uri) {
      return;
    }

    await processImage(result.assets[0].uri);
  }, [processImage]);

  /**
   * Reset to idle state
   */
  const reset = useCallback((): void => {
    setState({ status: 'idle' });
  }, []);

  return {
    state,
    pickAndScan,
    pickFromLibrary,
    reset,
    debugMode,
    toggleDebugMode,
  };
}
