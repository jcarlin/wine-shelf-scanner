/**
 * App configuration for Next.js web app
 *
 * Uses environment variables for configuration.
 * Set these in .env.local for development or Vercel dashboard for production.
 */

/**
 * Get API URL from environment
 */
function getApiBaseUrl(): string {
  // Check for environment variable
  const envUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (envUrl) {
    // Strip trailing slashes to prevent //path URLs
    return envUrl.replace(/\/+$/, '');
  }

  // Fallback based on environment
  if (process.env.NODE_ENV === 'development') {
    return 'http://localhost:8000';
  }

  // Production: Cloud Run
  return 'https://wine-scanner-api-82762985464.us-central1.run.app';
}

/**
 * Check if debug mode is enabled
 */
function isDebugMode(): boolean {
  return process.env.NEXT_PUBLIC_DEBUG_MODE === 'true';
}

/**
 * Check if mocks are enabled
 */
function getMocksEnabled(): boolean {
  return process.env.NEXT_PUBLIC_USE_MOCKS === 'true';
}

/**
 * App configuration
 */
export const Config = {
  /** API base URL for the wine scanner backend */
  API_BASE_URL: getApiBaseUrl(),

  /** Request timeout in milliseconds (Vision API can take 10-40s) */
  REQUEST_TIMEOUT: 45000,

  /** Image quality for compression (0-1) */
  IMAGE_QUALITY: 0.8,

  /** Enable debug mode to receive pipeline debug data from backend */
  DEBUG_MODE: isDebugMode(),

  /** Use mock service instead of real API */
  USE_MOCKS: getMocksEnabled(),

  /** Mock scenario to use when USE_MOCKS is true */
  MOCK_SCENARIO: 'full_shelf' as const,
} as const;

export type MockScenario = 'full_shelf' | 'partial_detection' | 'low_confidence' | 'empty_results';
