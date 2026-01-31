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
