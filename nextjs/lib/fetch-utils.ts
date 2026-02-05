/**
 * Fetch utilities with timeout support.
 *
 * Centralizes the pattern of using AbortController for timeouts
 * to avoid duplication across api-client.ts and report-client.ts.
 */

/**
 * Fetch with timeout support.
 *
 * @param url - URL to fetch
 * @param options - Standard fetch options
 * @param timeoutMs - Timeout in milliseconds
 * @returns Response if successful
 * @throws Error if aborted or network failure
 */
export async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Check if an error is an AbortError (timeout).
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}
