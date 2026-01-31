/**
 * API client for wine scanner backend
 */

import { Config } from './config';
import { ScanResponse } from './types';

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
 * Scan a wine shelf image
 *
 * @param imageUri - Local URI of the image to scan
 * @param options - Optional scan options (debug mode, etc.)
 * @returns Scan result with wine data or error
 */
export async function scanImage(
  imageUri: string,
  options: ScanOptions = {}
): Promise<ScanResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), Config.REQUEST_TIMEOUT);

  // Use debug from options, fall back to config
  const debug = options.debug ?? Config.DEBUG_MODE;

  try {
    // Create form data with image
    const formData = new FormData();

    // Extract filename from URI or use default
    const filename = imageUri.split('/').pop() ?? 'photo.jpg';

    // Append the image file - field name must be 'image' to match backend
    formData.append('image', {
      uri: imageUri,
      type: 'image/jpeg',
      name: filename,
    } as unknown as Blob);

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
