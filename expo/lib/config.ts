/**
 * App configuration
 */
export const Config = {
  /** API base URL for the wine scanner backend */
  API_BASE_URL: 'https://wine-scanner-api-82762985464.us-central1.run.app',

  /** Request timeout in milliseconds */
  REQUEST_TIMEOUT: 15000,

  /** Image quality for compression (0-1) */
  IMAGE_QUALITY: 0.8,
} as const;
