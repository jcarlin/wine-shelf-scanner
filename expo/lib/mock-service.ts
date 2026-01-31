/**
 * Mock service for development and testing
 * Ports iOS MockScanService scenarios to Expo
 */

import { ScanResponse, WineResult, FallbackWine } from './types';
import { MockScenario } from './config';

export interface MockServiceConfig {
  /** Simulated network delay in ms (default: 500, use 100 for tests) */
  delay?: number;
  /** Whether to simulate an error */
  simulateError?: boolean;
  /** Error message to return when simulating error */
  errorMessage?: string;
}

const DEFAULT_DELAY = 500;
const TEST_DELAY = 100;

/**
 * Generate a mock UUID-like string
 */
function mockId(): string {
  return `mock-${Math.random().toString(36).substring(2, 10)}`;
}

/**
 * Simulate network delay
 */
async function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get mock response for a scenario
 */
export async function getMockResponse(
  scenario: MockScenario,
  config: MockServiceConfig = {}
): Promise<ScanResponse> {
  const delayMs = config.delay ?? DEFAULT_DELAY;

  // Simulate network delay
  await delay(delayMs);

  // Simulate error if configured
  if (config.simulateError) {
    throw new Error(config.errorMessage ?? 'Mock error');
  }

  switch (scenario) {
    case 'full_shelf':
      return fullShelfResponse();
    case 'partial_detection':
      return partialDetectionResponse();
    case 'low_confidence':
      return lowConfidenceResponse();
    case 'empty_results':
      return emptyResultsResponse();
    default:
      return fullShelfResponse();
  }
}

/**
 * Get mock response with minimal delay for testing
 */
export async function getMockResponseForTest(
  scenario: MockScenario
): Promise<ScanResponse> {
  return getMockResponse(scenario, { delay: TEST_DELAY });
}

// MARK: - Mock Data

function fullShelfResponse(): ScanResponse {
  return {
    image_id: mockId(),
    results: [
      createWineResult('Caymus Cabernet Sauvignon', 4.5, 0.94, {
        x: 0.05,
        y: 0.15,
        width: 0.08,
        height: 0.35,
      }),
      createWineResult('Opus One', 4.8, 0.91, {
        x: 0.15,
        y: 0.12,
        width: 0.09,
        height: 0.38,
      }),
      createWineResult('Silver Oak Alexander Valley', 4.4, 0.88, {
        x: 0.26,
        y: 0.14,
        width: 0.08,
        height: 0.36,
      }),
      createWineResult('Jordan Cabernet Sauvignon', 4.3, 0.85, {
        x: 0.36,
        y: 0.13,
        width: 0.08,
        height: 0.37,
      }),
      createWineResult("Kendall-Jackson Vintner's Reserve", 3.8, 0.79, {
        x: 0.46,
        y: 0.16,
        width: 0.08,
        height: 0.34,
      }),
      createWineResult('La Crema Sonoma Coast Pinot Noir', 4.1, 0.72, {
        x: 0.56,
        y: 0.14,
        width: 0.08,
        height: 0.36,
      }),
      createWineResult('Meiomi Pinot Noir', 3.9, 0.68, {
        x: 0.66,
        y: 0.15,
        width: 0.08,
        height: 0.35,
      }),
      createWineResult('Bread & Butter Chardonnay', 3.7, 0.52, {
        x: 0.76,
        y: 0.17,
        width: 0.08,
        height: 0.33,
      }),
    ],
    fallback_list: [],
  };
}

function partialDetectionResponse(): ScanResponse {
  return {
    image_id: mockId(),
    results: [
      createWineResult('Caymus Cabernet Sauvignon', 4.5, 0.92, {
        x: 0.1,
        y: 0.15,
        width: 0.1,
        height: 0.35,
      }),
      createWineResult('Opus One', 4.8, 0.89, {
        x: 0.3,
        y: 0.12,
        width: 0.1,
        height: 0.38,
      }),
      createWineResult('Silver Oak Alexander Valley', 4.4, 0.86, {
        x: 0.5,
        y: 0.14,
        width: 0.1,
        height: 0.36,
      }),
    ],
    fallback_list: [
      createFallbackWine('Jordan Cabernet Sauvignon', 4.3),
      createFallbackWine("Kendall-Jackson Vintner's Reserve", 3.8),
      createFallbackWine('La Crema Sonoma Coast Pinot Noir', 4.1),
      createFallbackWine('Meiomi Pinot Noir', 3.9),
      createFallbackWine('Bread & Butter Chardonnay', 3.7),
    ],
  };
}

function lowConfidenceResponse(): ScanResponse {
  return {
    image_id: mockId(),
    results: [
      createWineResult('Unknown Red Wine', 3.5, 0.58, {
        x: 0.1,
        y: 0.15,
        width: 0.12,
        height: 0.35,
      }),
      createWineResult('Unknown White Wine', 3.3, 0.52, {
        x: 0.3,
        y: 0.12,
        width: 0.12,
        height: 0.38,
      }),
      createWineResult('Unknown Rose', 3.6, 0.48, {
        x: 0.5,
        y: 0.14,
        width: 0.12,
        height: 0.36,
      }),
      createWineResult('Unknown Sparkling', 3.4, 0.41, {
        x: 0.7,
        y: 0.13,
        width: 0.12,
        height: 0.37,
      }),
    ],
    fallback_list: [
      createFallbackWine('Possible Cabernet', 3.8),
      createFallbackWine('Possible Chardonnay', 3.5),
    ],
  };
}

function emptyResultsResponse(): ScanResponse {
  return {
    image_id: mockId(),
    results: [],
    fallback_list: [
      createFallbackWine('Caymus Cabernet Sauvignon', 4.5),
      createFallbackWine('Opus One', 4.8),
      createFallbackWine('Silver Oak Alexander Valley', 4.4),
      createFallbackWine('Jordan Cabernet Sauvignon', 4.3),
      createFallbackWine('La Crema Sonoma Coast Pinot Noir', 4.1),
      createFallbackWine('Meiomi Pinot Noir', 3.9),
      createFallbackWine("Kendall-Jackson Vintner's Reserve", 3.8),
      createFallbackWine('Bread & Butter Chardonnay', 3.7),
    ],
  };
}

// Helper functions

function createWineResult(
  name: string,
  rating: number,
  confidence: number,
  bbox: { x: number; y: number; width: number; height: number }
): WineResult {
  return {
    wine_name: name,
    rating,
    confidence,
    bbox,
  };
}

function createFallbackWine(name: string, rating: number): FallbackWine {
  return {
    wine_name: name,
    rating,
  };
}
