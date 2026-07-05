/**
 * API client for wine scanner backend (Web version)
 */

import { Config } from './config';
import { ScanResponse, ApiError, ScanResult, WineReviewsResponse } from './types';
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
      // Prefer the backend's human-readable detail (e.g. "scanner is busy,
      // try again in a moment") over a bare status code.
      let message = `Server returned ${response.status}`;
      try {
        const body = await response.json();
        if (body && typeof body.detail === 'string') {
          message = body.detail;
        } else if (body && typeof body.message === 'string') {
          message = body.message;
        }
      } catch {
        // Non-JSON error body — keep the generic message.
      }
      return {
        success: false,
        error: {
          type: 'SERVER_ERROR',
          message,
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

export interface ScanStreamOptions extends ScanOptions {
  /** Called with each cumulative partial ScanResponse as chunks complete */
  onPartial?: (partial: ScanResponse) => void;
}

/** Overall budget for a streaming scan (backend p95 ~19s + headroom) */
const STREAM_TIMEOUT_MS = 90000;

/**
 * Progressive scan via SSE (POST /scan/stream).
 *
 * Emits cumulative partial results through onPartial while the backend is
 * still reading labels; resolves with the final response. Falls back to
 * plain POST /scan when streaming is unavailable (older backend, proxies,
 * non-detect_read pipeline). If the stream dies after partials arrived,
 * resolves with the last partial rather than discarding rendered badges.
 */
export async function scanImageStream(
  file: File,
  options: ScanStreamOptions = {}
): Promise<ScanResult> {
  if (Config.USE_MOCKS) {
    return scanImage(file, options);
  }

  const formData = new FormData();
  formData.append('image', file, file.name);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

  let lastPartial: ScanResponse | null = null;

  try {
    const response = await fetch(`${Config.API_BASE_URL}/scan/stream`, {
      method: 'POST',
      body: formData,
      headers: { Accept: 'text/event-stream' },
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      // Endpoint missing/disabled (404/501) or proxy trouble — fall back.
      clearTimeout(timeout);
      return scanImage(file, options);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let errorMessage: string | null = null;

    const handleEvent = (block: string): ScanResponse | null => {
      let event: string | null = null;
      let data: string | null = null;
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim();
        else if (line.startsWith('data: ')) data = line.slice(6);
      }
      if (!event || data === null) return null;
      if (event === 'error') {
        try {
          errorMessage = (JSON.parse(data) as { message?: string }).message ?? null;
        } catch {
          errorMessage = null;
        }
        return null;
      }
      let parsed: ScanResponse;
      try {
        parsed = JSON.parse(data) as ScanResponse;
      } catch {
        return null;
      }
      if (event === 'done') return parsed;
      if (event === 'partial') {
        lastPartial = parsed;
        options.onPartial?.(parsed);
      }
      return null;
    };

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep;
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const final = handleEvent(block);
        if (final) {
          clearTimeout(timeout);
          return { success: true, data: final };
        }
        if (errorMessage !== null) break;
      }
      if (errorMessage !== null) break;
    }

    clearTimeout(timeout);

    // Stream ended without a done event (error event or connection cut).
    if (lastPartial) {
      // Keep what the user can already see rather than erroring out.
      return { success: true, data: lastPartial };
    }
    if (errorMessage !== null) {
      return {
        success: false,
        error: { type: 'SERVER_ERROR', message: errorMessage, status: 500 },
      };
    }
    // Nothing arrived at all — one plain-scan fallback.
    return scanImage(file, options);
  } catch (error) {
    clearTimeout(timeout);
    if (lastPartial) {
      return { success: true, data: lastPartial };
    }
    if (isAbortError(error)) {
      return {
        success: false,
        error: { type: 'TIMEOUT', message: 'Request timed out. Please try again.' },
      };
    }
    // Network/transport failure before any event — fall back once.
    return scanImage(file, options);
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
