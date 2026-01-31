import Constants from 'expo-constants';

/**
 * Get API URL based on environment
 *
 * Priority:
 * 1. Expo extra config (app.json/app.config.js)
 * 2. __DEV__ mode → localhost (for simulator/emulator)
 * 3. Production Cloud Run URL
 */
function getApiBaseUrl(): string {
  // Check for Expo config override
  const extraApiUrl = Constants.expoConfig?.extra?.apiBaseUrl;
  if (extraApiUrl) {
    return extraApiUrl;
  }

  // In dev mode, use localhost for iOS simulator
  // Note: Android emulator uses 10.0.2.2 for host localhost
  if (__DEV__) {
    // For iOS simulator, localhost works directly
    // For Android emulator, you'd need 10.0.2.2
    return 'http://localhost:8000';
  }

  // Production: Cloud Run
  return 'https://wine-scanner-api-82762985464.us-central1.run.app';
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
  DEBUG_MODE: __DEV__,

  /** Use mock service instead of real API */
  USE_MOCKS: false,

  /** Mock scenario to use when USE_MOCKS is true */
  MOCK_SCENARIO: 'full_shelf' as const,
} as const;

export type MockScenario = 'full_shelf' | 'partial_detection' | 'low_confidence' | 'empty_results';
