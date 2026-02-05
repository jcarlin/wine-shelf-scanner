'use client';

import { useState, useEffect, useCallback } from 'react';
import { checkServerHealth, HealthStatus } from '@/lib/api-client';

export type ServerHealthState =
  | { status: 'checking' }
  | { status: 'ready' }
  | { status: 'warming_up'; attempt: number }
  | { status: 'unavailable'; message: string };

const MAX_RETRY_ATTEMPTS = 30; // ~5 minutes with 10-second intervals
const DEFAULT_RETRY_INTERVAL = 10000; // 10 seconds

/**
 * Hook to check server health on mount and poll until ready
 *
 * This is designed for cold-start scenarios where Cloud Run has
 * minInstances=0 and needs to spin up a new instance.
 */
export function useServerHealth() {
  const [state, setState] = useState<ServerHealthState>({ status: 'checking' });

  const checkHealth = useCallback(async (attempt: number = 1) => {
    const result: HealthStatus = await checkServerHealth();

    if (result.status === 'healthy') {
      setState({ status: 'ready' });
      return;
    }

    if (result.status === 'warming_up') {
      if (attempt >= MAX_RETRY_ATTEMPTS) {
        setState({
          status: 'unavailable',
          message: 'Server is taking too long to start. Please try again later.',
        });
        return;
      }

      setState({ status: 'warming_up', attempt });

      // Schedule next check
      const retryInterval = (result.retryAfter || 10) * 1000;
      setTimeout(() => checkHealth(attempt + 1), Math.min(retryInterval, DEFAULT_RETRY_INTERVAL));
      return;
    }

    // Unavailable
    setState({
      status: 'unavailable',
      message: result.message || 'Server is unavailable',
    });
  }, []);

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);

  const retry = useCallback(() => {
    setState({ status: 'checking' });
    checkHealth();
  }, [checkHealth]);

  return { state, retry };
}
