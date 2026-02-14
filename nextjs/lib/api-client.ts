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

/**
 * Scan a wine shelf image via SSE streaming for progressive results.
 *
 * Sends a POST to /scan/stream and parses SSE events.
 * Calls onPhase1 when turbo-quality results arrive (~3.5s),
 * then onPhase2 when Gemini-enhanced results arrive (~6-8s).
 *
 * If streaming fails or is unavailable, falls back to regular scanImage().
 */
export async function scanImageStream(
  file: File,
  callbacks: {
    onPhase1: (data: ScanResponse) => void;
    onPhase2: (data: ScanResponse) => void;
    onMetadata?: (data: Record<string, Record<string, unknown>>) => void;
    onError: (error: ApiError) => void;
  },
  options: ScanOptions = {}
): Promise<void> {
  // Use mock service if configured — no streaming for mocks
  if (Config.USE_MOCKS) {
    const result = await scanImage(file, options);
    if (result.success) {
      callbacks.onPhase2(result.data);
    } else {
      callbacks.onError(result.error);
    }
    return;
  }

  const debug = options.debug ?? Config.DEBUG_MODE;
  const formData = new FormData();
  formData.append('image', file, file.name);

  const url = new URL(`${Config.API_BASE_URL}/scan/stream`);
  if (debug) {
    url.searchParams.set('debug', 'true');
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), Config.STREAM_TIMEOUT);

  try {
    const response = await fetch(url.toString(), {
      method: 'POST',
      body: formData,
      headers: { Accept: 'text/event-stream' },
      signal: controller.signal,
    });

    if (!response.ok) {
      callbacks.onError({
        type: 'SERVER_ERROR',
        message: `Server returned ${response.status}`,
        status: response.status,
      });
      return;
    }

    if (!response.body) {
      // No streaming support — fall back to regular scan
      const result = await scanImage(file, options);
      if (result.success) {
        callbacks.onPhase2(result.data);
      } else {
        callbacks.onError(result.error);
      }
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Parse SSE events from buffer
      const events = buffer.split('\n\n');
      // Keep the last incomplete chunk in the buffer
      buffer = events.pop() || '';

      for (const event of events) {
        if (!event.trim()) continue;

        let eventType = '';
        let eventData = '';

        for (const line of event.split('\n')) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          }
        }

        if (eventType === 'done') {
          return;
        }

        // Handle backend error events
        if (eventType === 'error' && eventData) {
          try {
            const errPayload = JSON.parse(eventData);
            callbacks.onError({
              type: 'SERVER_ERROR',
              message: errPayload.error || 'Pipeline error',
              status: 500,
            });
          } catch {
            callbacks.onError({
              type: 'SERVER_ERROR',
              message: 'Pipeline error',
              status: 500,
            });
          }
          // Don't return — backend sends 'done' next, let the loop exit naturally
        }

        if (eventData && (eventType === 'phase1' || eventType === 'phase2')) {
          try {
            const data = JSON.parse(eventData) as ScanResponse;
            if (eventType === 'phase1') {
              callbacks.onPhase1(data);
            } else {
              callbacks.onPhase2(data);
            }
          } catch {
            // Skip malformed JSON
          }
        }

        if (eventData && eventType === 'metadata' && callbacks.onMetadata) {
          try {
            const data = JSON.parse(eventData) as Record<string, Record<string, unknown>>;
            callbacks.onMetadata(data);
          } catch {
            // Skip malformed JSON
          }
        }
      }
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      callbacks.onError({
        type: 'TIMEOUT',
        message: 'Request timed out. Please try again.',
      });
    } else {
      callbacks.onError({
        type: 'NETWORK_ERROR',
        message: 'Unable to connect. Please check your internet connection.',
      });
    }
  } finally {
    clearTimeout(timeoutId);
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
