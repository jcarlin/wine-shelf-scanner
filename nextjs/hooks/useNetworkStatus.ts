'use client';

import { useState, useEffect, useCallback } from 'react';

export interface NetworkStatus {
  /** Whether the browser reports the device as online */
  isOnline: boolean;
  /** Whether the connection is metered (e.g., cellular) — only on supported browsers */
  isMetered: boolean;
  /** Effective connection type ('4g', '3g', '2g', 'slow-2g') — null if unsupported */
  effectiveType: string | null;
}

/**
 * Hook for monitoring network connectivity status.
 *
 * Uses navigator.onLine + online/offline events for connectivity,
 * and Network Information API for connection quality where available.
 */
export function useNetworkStatus(): NetworkStatus {
  const [status, setStatus] = useState<NetworkStatus>(() => getNetworkStatus());

  const update = useCallback(() => {
    setStatus(getNetworkStatus());
  }, []);

  useEffect(() => {
    window.addEventListener('online', update);
    window.addEventListener('offline', update);

    // Network Information API change event (Chrome/Edge/Android)
    const connection = getConnection();
    if (connection) {
      connection.addEventListener('change', update);
    }

    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
      if (connection) {
        connection.removeEventListener('change', update);
      }
    };
  }, [update]);

  return status;
}

function getNetworkStatus(): NetworkStatus {
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;
  const connection = getConnection();

  return {
    isOnline,
    isMetered: connection?.saveData === true,
    effectiveType: connection?.effectiveType ?? null,
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function getConnection(): any {
  if (typeof navigator === 'undefined') return null;
  return (
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (navigator as any).connection ??
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (navigator as any).mozConnection ??
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (navigator as any).webkitConnection ??
    null
  );
}
