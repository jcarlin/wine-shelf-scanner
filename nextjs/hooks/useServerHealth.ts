'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { checkServerHealth, HealthStatus } from '@/lib/api-client';

export type ServerHealthState =
  | { status: 'checking' }
  | { status: 'ready' }
  | { status: 'warming_up'; attempt: number }
  | { status: 'unavailable'; message: string };

const MAX_RETRY_ATTEMPTS = 30; // ~5 minutes with 10-second intervals
const DEFAULT_RETRY_INTERVAL = 10000; // 10 seconds
const CONFIRMATION_CHECKS = 2; // Extra health checks after first success
const CONFIRMATION_INTERVAL = 3000; // 3 seconds between confirmation checks

/**
 * Hook to check server health on mount and poll until ready
 *
 * This is designed for cold-start scenarios where Cloud Run has
 * minInstances=0 and needs to spin up a new instance.
 *
 * After the first successful health check, performs additional confirmation
 * checks to ensure the server is truly warmed up and stable (DB loaded, etc.)
 */
export function useServerHealth() {
  const [state, setState] = useState<ServerHealthState>({ status: 'checking' });
  const checkHealthRef = useRef<(attempt?: number) => Promise<void>>();

  useEffect(() => {
    const confirmReady = async (remaining: number): Promise<boolean> => {
      if (remaining <= 0) return true;
      await new Promise((r) => setTimeout(r, CONFIRMATION_INTERVAL));
      const check = await checkServerHealth();
      if (check.status !== 'healthy') return false;
      return confirmReady(remaining - 1);
    };

    const doCheck = async (attempt: number = 1) => {
      const result: HealthStatus = await checkServerHealth();

      if (result.status === 'healthy') {
        // Server responded healthy — run confirmation checks to make sure
        // it's truly warmed up (DB loaded, models ready, etc.)
        setState({ status: 'warming_up', attempt });
        const stable = await confirmReady(CONFIRMATION_CHECKS);
        if (stable) {
          setState({ status: 'ready' });
        } else {
          // Server was flaky, keep polling
          setTimeout(() => doCheck(attempt + 1), DEFAULT_RETRY_INTERVAL);
        }
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

        const retryInterval = (result.retryAfter || 10) * 1000;
        setTimeout(() => doCheck(attempt + 1), Math.min(retryInterval, DEFAULT_RETRY_INTERVAL));
        return;
      }

      // Unavailable
      setState({
        status: 'unavailable',
        message: result.message || 'Server is unavailable',
      });
    };

    checkHealthRef.current = doCheck;
    doCheck();
  }, []);

  const retry = useCallback(() => {
    setState({ status: 'checking' });
    checkHealthRef.current?.();
  }, []);

  return { state, retry };
}
