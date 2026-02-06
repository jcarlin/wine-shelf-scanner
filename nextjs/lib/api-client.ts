/**
 * API client for wine scanner backend (Web version)
 */

import { Config } from './config';
import { ScanResponse, ApiError, ScanResult, WineReviewsResponse } from './types';
import { getMockResponse } from './mock-service';
import { fetchWithTimeout, isAbortError } from './fetch-utils';

/** Timeout for health checks (ms) */
const HEALTH_CHECK_TIMEOUT_MS = 10000;

/** Max retries for transient scan failures (NETWORK_ERROR, TIMEOUT) */
const SCAN_MAX_RETRIES = 2;

/** Base delay between retries in ms (doubles each attempt: 2s, 4s) */
const SCAN_RETRY_BASE_DELAY_MS = 2000;

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
 * Retries up to SCAN_MAX_RETRIES times on transient failures
 * (NETWORK_ERROR, TIMEOUT) with exponential backoff.
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

  let lastResult: ScanResult | null = null;

  for (let attempt = 0; attempt <= SCAN_MAX_RETRIES; attempt++) {
    // Wait before retry (exponential backoff: 2s, 4s)
    if (attempt > 0) {
      await sleep(SCAN_RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1));
    }

    lastResult = await scanImageOnce(file, options);

    // Success or non-transient error — return immediately
    if (
      lastResult.success ||
      (lastResult.error.type !== 'NETWORK_ERROR' && lastResult.error.type !== 'TIMEOUT')
    ) {
      return lastResult;
    }
  }

  return lastResult!;
}

/** Single scan attempt (no retry). */
async function scanImageOnce(
  file: File,
  options: ScanOptions
): Promise<ScanResult> {
  // Use debug from options, fall back to config
  const debug = options.debug ?? Config.DEBUG_MODE;

  // Adapt image quality based on network conditions (matches iOS NetworkMonitor behavior)
  const uploadFile = await maybeCompressForNetwork(file);

  // Create form data with image file
  const formData = new FormData();
  formData.append('image', uploadFile, file.name);

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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Compress image for upload when on a slow/metered connection.
 * Uses the Network Information API where available.
 * On fast connections or when API is unsupported, returns the original file.
 */
async function maybeCompressForNetwork(file: File): Promise<Blob> {
  // Only compress JPEG/PNG — other types (HEIC) are handled separately
  if (!file.type.startsWith('image/jpeg') && !file.type.startsWith('image/png')) {
    return file;
  }

  const quality = getNetworkAdaptiveQuality();
  if (quality >= 0.8) return file; // Good connection, no compression needed

  try {
    const bitmap = await createImageBitmap(file);
    // Scale down on very slow connections
    const maxDim = quality <= 0.5 ? 1200 : 1600;
    const scale = Math.min(1, maxDim / Math.max(bitmap.width, bitmap.height));
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = new OffscreenCanvas(width, height);
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;

    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();

    return canvas.convertToBlob({ type: 'image/jpeg', quality });
  } catch {
    return file; // Compression failed, use original
  }
}

/**
 * Get adaptive JPEG quality based on network conditions.
 * Mirrors iOS NetworkMonitor.compressionQuality behavior.
 */
function getNetworkAdaptiveQuality(): number {
  if (typeof navigator === 'undefined') return 0.8;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const conn = (navigator as any).connection;
  if (!conn) return 0.8; // API not supported — assume good connection

  // Data saver mode enabled
  if (conn.saveData) return 0.5;

  // Adapt based on effective connection type
  switch (conn.effectiveType) {
    case 'slow-2g':
    case '2g':
      return 0.4;
    case '3g':
      return 0.6;
    default: // '4g' or unknown
      return 0.8;
  }
}

/** Timeout for review fetches (ms) */
const REVIEWS_TIMEOUT_MS = 10000;

/**
 * Fetch reviews for a specific wine by database ID.
 *
 * @param wineId - Wine database ID (from WineResult.wine_id)
 * @param options - Optional query params (limit, textOnly)
 * @returns WineReviewsResponse or null if not found / error
 */
export async function fetchWineReviews(
  wineId: number,
  options: { limit?: number; textOnly?: boolean } = {}
): Promise<WineReviewsResponse | null> {
  if (Config.USE_MOCKS) {
    return null;
  }

  const url = new URL(`${Config.API_BASE_URL}/wines/${wineId}/reviews`);
  if (options.limit !== undefined) {
    url.searchParams.set('limit', String(options.limit));
  }
  if (options.textOnly !== undefined) {
    url.searchParams.set('text_only', String(options.textOnly));
  }

  try {
    const response = await fetchWithTimeout(
      url.toString(),
      {
        method: 'GET',
        headers: { Accept: 'application/json' },
      },
      REVIEWS_TIMEOUT_MS
    );

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as WineReviewsResponse;
  } catch {
    return null;
  }
}
