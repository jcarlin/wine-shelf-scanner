/**
 * Hook for rotating through tips at a set interval.
 *
 * Used by ProcessingSpinner and ScanningOverlay to show rotating tips
 * while the user waits for scanning to complete.
 */

import { useState, useEffect } from 'react';

/** Default interval for tip rotation in milliseconds */
export const TIP_ROTATION_INTERVAL_MS = 3000;

/**
 * Rotate through tips at a set interval.
 *
 * @param tipCount - Number of tips to rotate through
 * @param intervalMs - Rotation interval in milliseconds (default: 3000)
 * @returns Current tip index (0-based)
 */
export function useTipRotation(
  tipCount: number,
  intervalMs: number = TIP_ROTATION_INTERVAL_MS
): number {
  const [tipIndex, setTipIndex] = useState(0);

  useEffect(() => {
    if (tipCount <= 1) return;

    const interval = setInterval(() => {
      setTipIndex((prev) => (prev + 1) % tipCount);
    }, intervalMs);

    return () => clearInterval(interval);
  }, [tipCount, intervalMs]);

  return tipIndex;
}
