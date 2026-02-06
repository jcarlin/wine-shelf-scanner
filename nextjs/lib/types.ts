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

export interface RatingSourceDetail {
  source_name: string;
  display_name: string;
  original_rating: number;
  scale_label: string;
}

export interface WineResult {
  wine_name: string;
  wine_id?: number;    // Database ID (for fetching reviews via /wines/{id}/reviews)
  rating: number | null;
  confidence: number;
  bbox: BoundingBox;
  // Extended metadata (optional - populated from DB or LLM)
  wine_type?: string;  // 'Red', 'White', 'Rosé', 'Sparkling', etc.
  brand?: string;      // Winery or brand name
  region?: string;     // Wine region (e.g., 'Napa Valley', 'Burgundy')
  varietal?: string;   // Grape varietal (e.g., 'Cabernet Sauvignon')
  blurb?: string;      // Brief description of the wine or producer
  review_count?: number;        // Number of reviews
  review_snippets?: string[];   // Sample review quotes
  // Feature-flagged fields (null when feature is off)
  is_safe_pick?: boolean;       // Crowd favorite badge
  pairing?: string;             // Food pairing suggestion
  rating_sources?: RatingSourceDetail[];  // Rating provenance details
}

// MARK: - Wine Reviews Types

export interface ReviewItem {
  source_name: string;
  reviewer?: string | null;
  rating?: number | null;
  review_text?: string | null;
  review_date?: string | null;
  vintage?: string | null;
}

export interface WineReviewsResponse {
  wine_id: number;
  wine_name: string;
  total_reviews: number;
  text_reviews: number;
  avg_rating?: number | null;
  reviews: ReviewItem[];
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
  | { status: 'processing'; imageUri: string | null }
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

export interface NearMissCandidate {
  wine_name: string;
  score: number;
  rejection_reason: string;
}

export interface FuzzyMatchDebug {
  candidate: string | null;
  scores: FuzzyMatchScores | null;
  rating: number | null;
  near_misses?: NearMissCandidate[];
  fts_candidates_count?: number;
  rejection_reason?: string | null;
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

export interface NormalizationTrace {
  original_text: string;
  after_pattern_removal: string;
  removed_patterns: string[];
  removed_filler_words: string[];
  final_text: string;
}

export interface LLMRawDebug {
  prompt_text: string;
  raw_response: string;
  model_used: string | null;
  was_heuristic_fallback: boolean;
}

export interface DebugPipelineStep {
  raw_text: string;
  normalized_text: string;
  bottle_index: number | null;
  fuzzy_match: FuzzyMatchDebug | null;
  llm_validation: LLMValidationDebug | null;
  normalization_trace?: NormalizationTrace | null;
  llm_raw?: LLMRawDebug | null;
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

// MARK: - API Error Types

/** Error types returned by API client */
export type ApiError =
  | { type: 'NETWORK_ERROR'; message: string }
  | { type: 'SERVER_ERROR'; message: string; status: number }
  | { type: 'TIMEOUT'; message: string }
  | { type: 'PARSE_ERROR'; message: string };

/** Discriminated union for scan results */
export type ScanResult =
  | { success: true; data: ScanResponse }
  | { success: false; error: ApiError };

// MARK: - Bug Report Types

export type BugReportType = 'error' | 'partial_detection' | 'full_failure' | 'wrong_wine';

export type BugReportErrorType = 'NETWORK_ERROR' | 'SERVER_ERROR' | 'TIMEOUT' | 'PARSE_ERROR';

export interface BugReportMetadata {
  wines_detected?: number;
  wines_in_fallback?: number;
  confidence_scores?: number[];
  debug_data?: Record<string, unknown>;
}

export interface BugReportRequest {
  report_type: BugReportType;
  error_type?: BugReportErrorType | null;
  error_message?: string | null;
  user_description?: string | null;
  image_id?: string | null;
  device_id: string;
  platform: string;
  app_version?: string | null;
  timestamp?: string | null;
  metadata?: BugReportMetadata | null;
}

export interface BugReportResponse {
  success: boolean;
  report_id: string;
}
