/**
 * Mock service for development and testing
 * Mock service for development and testing
 */

import {
  ScanResponse,
  WineResult,
  FallbackWine,
  DebugData,
  DebugPipelineStep,
  FuzzyMatchScores,
} from './types';
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
  const wines = [
    { name: 'Caymus Cabernet Sauvignon', rating: 4.5, confidence: 0.94, raw: 'CAYMUS CABERNET SAUVIGNON 2019 NAPA VALLEY' },
    { name: 'Opus One', rating: 4.8, confidence: 0.91, raw: 'OPUS ONE 2018 NAPA VALLEY' },
    { name: 'Silver Oak Alexander Valley', rating: 4.4, confidence: 0.88, raw: 'SILVER OAK ALEXANDER VALLEY CABERNET' },
    { name: 'Jordan Cabernet Sauvignon', rating: 4.3, confidence: 0.85, raw: 'JORDAN CABERNET SAUVIGNON ALEXANDER VALLEY' },
    { name: "Kendall-Jackson Vintner's Reserve", rating: 3.8, confidence: 0.79, raw: 'KENDALL JACKSON VINTNERS RESERVE CHARDONNAY' },
    { name: 'La Crema Sonoma Coast Pinot Noir', rating: 4.1, confidence: 0.72, raw: 'LA CREMA PINOT NOIR SONOMA COAST' },
    { name: 'Meiomi Pinot Noir', rating: 3.9, confidence: 0.68, raw: 'MEIOMI PINOT NOIR CALIFORNIA' },
    { name: 'Bread & Butter Chardonnay', rating: 3.7, confidence: 0.52, raw: 'BREAD BUTTER CHARDONNAY' },
  ];

  const bboxes = [
    { x: 0.05, y: 0.15, width: 0.08, height: 0.35 },
    { x: 0.15, y: 0.12, width: 0.09, height: 0.38 },
    { x: 0.26, y: 0.14, width: 0.08, height: 0.36 },
    { x: 0.36, y: 0.13, width: 0.08, height: 0.37 },
    { x: 0.46, y: 0.16, width: 0.08, height: 0.34 },
    { x: 0.56, y: 0.14, width: 0.08, height: 0.36 },
    { x: 0.66, y: 0.15, width: 0.08, height: 0.35 },
    { x: 0.76, y: 0.17, width: 0.08, height: 0.33 },
  ];

  return {
    image_id: mockId(),
    results: wines.map((w, i) => createWineResult(w.name, w.rating, w.confidence, bboxes[i])),
    fallback_list: [],
    debug: createDebugData(wines, 0),
  };
}

function partialDetectionResponse(): ScanResponse {
  const matchedWines = [
    { name: 'Caymus Cabernet Sauvignon', rating: 4.5, confidence: 0.92, raw: 'CAYMUS CABERNET SAUVIGNON 2019' },
    { name: 'Opus One', rating: 4.8, confidence: 0.89, raw: 'OPUS ONE 2018' },
    { name: 'Silver Oak Alexander Valley', rating: 4.4, confidence: 0.86, raw: 'SILVER OAK ALEXANDER VALLEY' },
  ];

  const failedTexts = [
    { raw: 'JORDAN CAB...', normalized: 'jordan cab' },
    { raw: 'KJ VINT...', normalized: 'kj vint' },
  ];

  return {
    image_id: mockId(),
    results: [
      createWineResult('Caymus Cabernet Sauvignon', 4.5, 0.92, { x: 0.1, y: 0.15, width: 0.1, height: 0.35 }),
      createWineResult('Opus One', 4.8, 0.89, { x: 0.3, y: 0.12, width: 0.1, height: 0.38 }),
      createWineResult('Silver Oak Alexander Valley', 4.4, 0.86, { x: 0.5, y: 0.14, width: 0.1, height: 0.36 }),
    ],
    fallback_list: [
      createFallbackWine('Jordan Cabernet Sauvignon', 4.3),
      createFallbackWine("Kendall-Jackson Vintner's Reserve", 3.8),
      createFallbackWine('La Crema Sonoma Coast Pinot Noir', 4.1),
      createFallbackWine('Meiomi Pinot Noir', 3.9),
      createFallbackWine('Bread & Butter Chardonnay', 3.7),
    ],
    debug: createDebugDataPartial(matchedWines, failedTexts),
  };
}

function lowConfidenceResponse(): ScanResponse {
  const wines = [
    { name: 'Unknown Red Wine', rating: 3.5, confidence: 0.58, raw: 'RED WINE TABLE', usedLlm: true },
    { name: 'Unknown White Wine', rating: 3.3, confidence: 0.52, raw: 'WHITE WINE', usedLlm: true },
    { name: 'Unknown Rose', rating: 3.6, confidence: 0.48, raw: 'ROSE WINE FRANCE', usedLlm: false },
    { name: 'Unknown Sparkling', rating: 3.4, confidence: 0.41, raw: 'SPARKLING WINE', usedLlm: false },
  ];

  return {
    image_id: mockId(),
    results: [
      createWineResult('Unknown Red Wine', 3.5, 0.58, { x: 0.1, y: 0.15, width: 0.12, height: 0.35 }),
      createWineResult('Unknown White Wine', 3.3, 0.52, { x: 0.3, y: 0.12, width: 0.12, height: 0.38 }),
      createWineResult('Unknown Rose', 3.6, 0.48, { x: 0.5, y: 0.14, width: 0.12, height: 0.36 }),
      createWineResult('Unknown Sparkling', 3.4, 0.41, { x: 0.7, y: 0.13, width: 0.12, height: 0.37 }),
    ],
    fallback_list: [
      createFallbackWine('Possible Cabernet', 3.8),
      createFallbackWine('Possible Chardonnay', 3.5),
    ],
    debug: createDebugDataLowConfidence(wines),
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
    debug: createDebugDataEmpty(),
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

// MARK: - Debug Data Helpers

interface MockWineData {
  name: string;
  rating: number;
  confidence: number;
  raw: string;
  usedLlm?: boolean;
}

interface MockFailedText {
  raw: string;
  normalized: string;
}

function createFuzzyScores(confidence: number): FuzzyMatchScores {
  // Generate realistic fuzzy match scores based on confidence
  const baseScore = confidence * 0.9 + 0.1;
  return {
    ratio: Math.min(1, baseScore + Math.random() * 0.1),
    partial_ratio: Math.min(1, baseScore + Math.random() * 0.15),
    token_sort_ratio: Math.min(1, baseScore + Math.random() * 0.12),
    phonetic_bonus: Math.random() * 0.05,
    weighted_score: confidence,
  };
}

function createPipelineStep(
  wine: MockWineData,
  index: number,
  useLlm: boolean = false
): DebugPipelineStep {
  const normalized = wine.raw
    .toLowerCase()
    .replace(/\d{4}/g, '')
    .replace(/750ml|1l/gi, '')
    .trim();

  return {
    raw_text: wine.raw,
    normalized_text: normalized,
    bottle_index: index,
    fuzzy_match: {
      candidate: wine.name,
      scores: createFuzzyScores(wine.confidence),
      rating: wine.rating,
    },
    llm_validation: useLlm
      ? {
          is_valid_match: true,
          wine_name: wine.name,
          confidence: wine.confidence,
          reasoning: 'LLM confirmed match based on label text patterns',
        }
      : null,
    final_result: {
      wine_name: wine.name,
      confidence: wine.confidence,
      source: useLlm ? 'llm' : 'fuzzy',
    },
    step_failed: false,
    included_in_results: wine.confidence >= 0.45,
  };
}

function createFailedPipelineStep(
  text: MockFailedText,
  index: number
): DebugPipelineStep {
  return {
    raw_text: text.raw,
    normalized_text: text.normalized,
    bottle_index: index,
    fuzzy_match: {
      candidate: 'Unknown Wine',
      scores: {
        ratio: 0.25,
        partial_ratio: 0.35,
        token_sort_ratio: 0.28,
        phonetic_bonus: 0,
        weighted_score: 0.29,
      },
      rating: null,
    },
    llm_validation: {
      is_valid_match: false,
      wine_name: null,
      confidence: null,
      reasoning: 'Insufficient text for wine identification',
    },
    final_result: null,
    step_failed: true,
    included_in_results: false,
  };
}

function createDebugData(wines: MockWineData[], llmCalls: number): DebugData {
  const pipelineSteps = wines.map((w, i) => createPipelineStep(w, i));
  const includedCount = pipelineSteps.filter((s) => s.included_in_results).length;

  return {
    pipeline_steps: pipelineSteps,
    total_ocr_texts: wines.length,
    bottles_detected: wines.length,
    texts_matched: includedCount,
    llm_calls_made: llmCalls,
  };
}

function createDebugDataPartial(
  matchedWines: MockWineData[],
  failedTexts: MockFailedText[]
): DebugData {
  const matchedSteps = matchedWines.map((w, i) => createPipelineStep(w, i));
  const failedSteps = failedTexts.map((t, i) =>
    createFailedPipelineStep(t, matchedWines.length + i)
  );
  const allSteps = [...matchedSteps, ...failedSteps];

  return {
    pipeline_steps: allSteps,
    total_ocr_texts: allSteps.length,
    bottles_detected: matchedWines.length + failedTexts.length,
    texts_matched: matchedWines.length,
    llm_calls_made: failedTexts.length, // LLM tried on failed texts
  };
}

function createDebugDataLowConfidence(wines: MockWineData[]): DebugData {
  const llmCount = wines.filter((w) => w.usedLlm).length;
  const pipelineSteps = wines.map((w, i) =>
    createPipelineStep(w, i, w.usedLlm ?? false)
  );

  return {
    pipeline_steps: pipelineSteps,
    total_ocr_texts: wines.length,
    bottles_detected: wines.length,
    texts_matched: wines.filter((w) => w.confidence >= 0.45).length,
    llm_calls_made: llmCount,
  };
}

function createDebugDataEmpty(): DebugData {
  const failedTexts = [
    { raw: 'WINE SHOP...', normalized: 'wine shop' },
    { raw: 'PRICE TAG $12.99', normalized: 'price tag' },
    { raw: 'SHELF LABEL', normalized: 'shelf label' },
  ];

  return {
    pipeline_steps: failedTexts.map((t, i) => createFailedPipelineStep(t, i)),
    total_ocr_texts: failedTexts.length,
    bottles_detected: 0,
    texts_matched: 0,
    llm_calls_made: failedTexts.length,
  };
}
