/**
 * API client for wine scanner backend (Web version)
 */

import { Config } from './config';
import { ScanResponse, ApiError, ScanResult } from './types';
import { getMockResponse } from './mock-service';
import { fetchWithTimeout, isAbortError } from './fetch-utils';

/** Timeout for health checks (ms) */
const HEALTH_CHECK_TIMEOUT_MS = 10000;

export type HealthStatus =
  | { status: 'healthy' }
  | { status: 'warming_up'; retryAfter?: number }
  | { status: 'unavailable'; message: string };

/**
 * Check if the backend server is healthy and ready to accept requests
 *
 * @returns Health status of the server
 */
export async function checkServerHealth(): Promise<HealthStatus> {
  // In mock mode, always report healthy
  if (Config.USE_MOCKS) {
    return { status: 'healthy' };
  }

  try {
    const response = await fetchWithTimeout(
      `${Config.API_BASE_URL}/health`,
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
      },
      HEALTH_CHECK_TIMEOUT_MS
    );

    if (response.ok) {
      return { status: 'healthy' };
    }

    // 503 means server is warming up
    if (response.status === 503) {
      const retryAfter = response.headers.get('Retry-After');
      return {
        status: 'warming_up',
        retryAfter: retryAfter ? parseInt(retryAfter, 10) : 10,
      };
    }

    return {
      status: 'unavailable',
      message: `Server returned ${response.status}`,
    };
  } catch (error) {
    if (isAbortError(error)) {
      return {
        status: 'unavailable',
        message: 'Health check timed out',
      };
    }

    // Network error likely means server is cold starting
    return {
      status: 'warming_up',
      retryAfter: 5,
    };
  }
}

// ApiError and ScanResult are re-exported from types.ts
export type { ApiError, ScanResult } from './types';

export interface ScanOptions {
  /** Enable debug mode to receive pipeline debug data */
  debug?: boolean;
}

/**
 * Scan a wine shelf image (Web version)
 *
 * @param file - File object from file input
 * @param options - Optional scan options (debug mode, etc.)
 * @returns Scan result with wine data or error
 */
export async function scanImage(
  file: File,
  options: ScanOptions = {}
): Promise<ScanResult> {
  // Use mock service if configured
  if (Config.USE_MOCKS) {
    try {
      const response = await getMockResponse(Config.MOCK_SCENARIO);
      return { success: true, data: response };
    } catch (error) {
      return {
        success: false,
        error: {
          type: 'NETWORK_ERROR',
          message: error instanceof Error ? error.message : 'Mock service error',
        },
      };
    }
  }

  // Use debug from options, fall back to config
  const debug = options.debug ?? Config.DEBUG_MODE;

  // Create form data with image file
  const formData = new FormData();
  formData.append('image', file, file.name);

  // Build URL with optional debug query param
  const url = new URL(`${Config.API_BASE_URL}/scan`);
  if (debug) {
    url.searchParams.set('debug', 'true');
  }

  try {
    const response = await fetchWithTimeout(
      url.toString(),
      {
        method: 'POST',
        body: formData,
        headers: { Accept: 'application/json' },
      },
      Config.REQUEST_TIMEOUT
    );

    if (!response.ok) {
      return {
        success: false,
        error: {
          type: 'SERVER_ERROR',
          message: `Server returned ${response.status}`,
          status: response.status,
        },
      };
    }

    const data = await response.json();
    return { success: true, data: data as ScanResponse };
  } catch (error) {
    if (isAbortError(error)) {
      return {
        success: false,
        error: {
          type: 'TIMEOUT',
          message: 'Request timed out. Please try again.',
        },
      };
    }

    if (error instanceof Error) {
      // Network errors (no connection, DNS failure, etc.)
      return {
        success: false,
        error: {
          type: 'NETWORK_ERROR',
          message: 'Unable to connect. Please check your internet connection.',
        },
      };
    }

    return {
      success: false,
      error: {
        type: 'PARSE_ERROR',
        message: 'An unexpected error occurred.',
      },
    };
  }
}
