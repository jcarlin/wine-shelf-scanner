/**
 * API types matching backend contract
 *
 * API Contract (DO NOT CHANGE):
 * {
 *   "image_id": "string",
 *   "results": [{
 *     "wine_name": "string",
 *     "rating": 4.6,
 *     "confidence": 0.92,
 *     "bbox": { "x": 0.25, "y": 0.40, "width": 0.10, "height": 0.30 }
 *   }],
 *   "fallback_list": [{ "wine_name": "string", "rating": 4.3 }]
 * }
 */

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface WineResult {
  wine_name: string;
  rating: number | null;
  confidence: number;
  bbox: BoundingBox;
}

export interface FallbackWine {
  wine_name: string;
  rating: number;
}

export interface ScanResponse {
  image_id: string;
  results: WineResult[];
  fallback_list: FallbackWine[];
  debug?: DebugData;
}

export type ScanState =
  | { status: 'idle' }
  | { status: 'processing' }
  | { status: 'results'; response: ScanResponse; imageUri: string }
  | { status: 'error'; message: string };

export interface Size {
  width: number;
  height: number;
}

export interface Point {
  x: number;
  y: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

// MARK: - Debug Types (matching iOS ScanResponse.swift)

export interface FuzzyMatchScores {
  ratio: number;
  partial_ratio: number;
  token_sort_ratio: number;
  phonetic_bonus: number;
  weighted_score: number;
}

export interface FuzzyMatchDebug {
  candidate: string;
  scores: FuzzyMatchScores;
  rating: number | null;
}

export interface LLMValidationDebug {
  is_valid_match: boolean;
  wine_name: string | null;
  confidence: number | null;
  reasoning: string | null;
}

export interface DebugFinalResult {
  wine_name: string;
  confidence: number;
  source: 'fuzzy' | 'llm' | 'none';
}

export interface DebugPipelineStep {
  raw_text: string;
  normalized_text: string;
  bottle_index: number | null;
  fuzzy_match: FuzzyMatchDebug | null;
  llm_validation: LLMValidationDebug | null;
  final_result: DebugFinalResult | null;
  step_failed: boolean;
  included_in_results: boolean;
}

export interface DebugData {
  pipeline_steps: DebugPipelineStep[];
  total_ocr_texts: number;
  bottles_detected: number;
  texts_matched: number;
  llm_calls_made: number;
}
