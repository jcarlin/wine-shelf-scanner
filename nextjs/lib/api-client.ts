/**
 * API client for wine scanner backend (Web version)
 */

import { Config } from './config';
import { ScanResponse } from './types';
import { getMockResponse } from './mock-service';

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

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout for health check

  try {
    const response = await fetch(`${Config.API_BASE_URL}/health`, {
      method: 'GET',
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
      },
    });

    clearTimeout(timeoutId);

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
    clearTimeout(timeoutId);

    if (error instanceof Error && error.name === 'AbortError') {
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

export type ApiError =
  | { type: 'NETWORK_ERROR'; message: string }
  | { type: 'SERVER_ERROR'; message: string; status: number }
  | { type: 'TIMEOUT'; message: string }
  | { type: 'PARSE_ERROR'; message: string };

export type ScanResult =
  | { success: true; data: ScanResponse }
  | { success: false; error: ApiError };

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

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), Config.REQUEST_TIMEOUT);

  // Use debug from options, fall back to config
  const debug = options.debug ?? Config.DEBUG_MODE;

  try {
    // Create form data with image file
    const formData = new FormData();
    formData.append('image', file, file.name);

    // Build URL with optional debug query param
    const url = new URL(`${Config.API_BASE_URL}/scan`);
    if (debug) {
      url.searchParams.set('debug', 'true');
    }

    const response = await fetch(url.toString(), {
      method: 'POST',
      body: formData,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
      },
    });

    clearTimeout(timeoutId);

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
    clearTimeout(timeoutId);

    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        return {
          success: false,
          error: {
            type: 'TIMEOUT',
            message: 'Request timed out. Please try again.',
          },
        };
      }

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
