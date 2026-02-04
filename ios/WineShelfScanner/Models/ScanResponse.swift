import Foundation
import CoreGraphics
import SwiftUI

/// Response from the /scan API endpoint
///
/// API Contract (DO NOT CHANGE):
/// ```json
/// {
///   "image_id": "string",
///   "results": [{
///     "wine_name": "string",
///     "rating": 4.6,
///     "confidence": 0.92,
///     "bbox": { "x": 0.25, "y": 0.40, "width": 0.10, "height": 0.30 }
///   }],
///   "fallback_list": [{ "wine_name": "string", "rating": 4.3 }]
/// }
/// ```
struct ScanResponse: Codable, Equatable {
    let imageId: String
    let results: [WineResult]
    let fallbackList: [FallbackWine]
    let debug: DebugData?

    enum CodingKeys: String, CodingKey {
        case imageId = "image_id"
        case results
        case fallbackList = "fallback_list"
        case debug
    }
}

/// Detail about where a wine's rating comes from
struct RatingSourceDetail: Codable, Equatable {
    let sourceName: String
    let displayName: String
    let originalRating: Double
    let scaleLabel: String

    enum CodingKeys: String, CodingKey {
        case sourceName = "source_name"
        case displayName = "display_name"
        case originalRating = "original_rating"
        case scaleLabel = "scale_label"
    }
}

/// A detected wine bottle with rating and position
struct WineResult: Codable, Equatable, Identifiable {
    let wineName: String
    let rating: Double?
    let confidence: Double
    let bbox: BoundingBox
    // Extended metadata (optional - populated from DB or LLM)
    var wineType: String? = nil       // 'Red', 'White', 'Rosé', 'Sparkling', etc.
    var brand: String? = nil          // Winery or brand name
    var region: String? = nil         // Wine region (e.g., 'Napa Valley', 'Burgundy')
    var varietal: String? = nil       // Grape varietal (e.g., 'Cabernet Sauvignon')
    var blurb: String? = nil          // Brief description of the wine or producer
    var reviewCount: Int? = nil       // Number of reviews
    var reviewSnippets: [String]? = nil  // Sample review quotes
    // Feature-flagged fields (null when feature is off)
    var isSafePick: Bool? = nil       // Crowd favorite badge
    var pairing: String? = nil        // Food pairing suggestion
    var ratingSources: [RatingSourceDetail]? = nil  // Rating provenance details

    /// Unique ID combining name + full bbox (handles duplicate wines on shelf)
    var id: String { "\(wineName)_\(bbox.x)_\(bbox.y)_\(bbox.width)_\(bbox.height)" }

    enum CodingKeys: String, CodingKey {
        case wineName = "wine_name"
        case rating
        case confidence
        case bbox
        case wineType = "wine_type"
        case brand
        case region
        case varietal
        case blurb
        case reviewCount = "review_count"
        case reviewSnippets = "review_snippets"
        case isSafePick = "is_safe_pick"
        case pairing
        case ratingSources = "rating_sources"
    }
}

/// Normalized bounding box (0-1 range)
struct BoundingBox: Codable, Equatable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double

    /// Convert to CGRect for SwiftUI
    var cgRect: CGRect {
        CGRect(x: x, y: y, width: width, height: height)
    }
}

/// Wine in fallback list (no position data)
struct FallbackWine: Codable, Equatable, Identifiable {
    let wineName: String
    let rating: Double?

    var id: String { wineName }

    enum CodingKeys: String, CodingKey {
        case wineName = "wine_name"
        case rating
    }
}

// MARK: - Debug Types

/// Individual scores from fuzzy matching algorithms
struct FuzzyMatchScores: Codable, Equatable {
    let ratio: Double
    let partialRatio: Double
    let tokenSortRatio: Double
    let phoneticBonus: Double
    let weightedScore: Double

    enum CodingKeys: String, CodingKey {
        case ratio
        case partialRatio = "partial_ratio"
        case tokenSortRatio = "token_sort_ratio"
        case phoneticBonus = "phonetic_bonus"
        case weightedScore = "weighted_score"
    }
}

/// Debug info for fuzzy match step
struct FuzzyMatchDebug: Codable, Equatable {
    let candidate: String?
    let scores: FuzzyMatchScores?
    let rating: Double?
}

/// Debug info for LLM validation step
struct LLMValidationDebug: Codable, Equatable {
    let isValidMatch: Bool
    let wineName: String?
    let confidence: Double
    let reasoning: String

    enum CodingKeys: String, CodingKey {
        case isValidMatch = "is_valid_match"
        case wineName = "wine_name"
        case confidence
        case reasoning
    }
}

/// Final result info for debug step
struct DebugFinalResult: Codable, Equatable {
    let wineName: String
    let confidence: Double
    let source: String

    enum CodingKeys: String, CodingKey {
        case wineName = "wine_name"
        case confidence
        case source
    }
}

/// Debug info for a single OCR text through the pipeline
struct DebugPipelineStep: Codable, Equatable, Identifiable {
    let rawText: String
    let normalizedText: String
    let bottleIndex: Int
    let fuzzyMatch: FuzzyMatchDebug?
    let llmValidation: LLMValidationDebug?
    let finalResult: DebugFinalResult?
    let stepFailed: String?
    let includedInResults: Bool

    var id: String { "\(bottleIndex)_\(rawText.prefix(20))" }

    enum CodingKeys: String, CodingKey {
        case rawText = "raw_text"
        case normalizedText = "normalized_text"
        case bottleIndex = "bottle_index"
        case fuzzyMatch = "fuzzy_match"
        case llmValidation = "llm_validation"
        case finalResult = "final_result"
        case stepFailed = "step_failed"
        case includedInResults = "included_in_results"
    }

    /// Status for display (success/warning/failure)
    var status: DebugStepStatus {
        if includedInResults {
            return .success
        } else if fuzzyMatch?.candidate != nil || llmValidation?.wineName != nil {
            return .warning  // Matched but excluded
        } else {
            return .failure
        }
    }
}

/// Status enum for debug step display
enum DebugStepStatus {
    case success   // Included in results (green checkmark)
    case warning   // Matched but excluded (yellow warning)
    case failure   // Failed to match (red X)
}

/// Complete debug information for a scan
struct DebugData: Codable, Equatable {
    let pipelineSteps: [DebugPipelineStep]
    let totalOcrTexts: Int
    let bottlesDetected: Int
    let textsMatched: Int
    let llmCallsMade: Int

    enum CodingKeys: String, CodingKey {
        case pipelineSteps = "pipeline_steps"
        case totalOcrTexts = "total_ocr_texts"
        case bottlesDetected = "bottles_detected"
        case textsMatched = "texts_matched"
        case llmCallsMade = "llm_calls_made"
    }
}

// MARK: - Convenience Extensions

extension ScanResponse {
    /// Returns wines sorted by rating (highest first, nil ratings last)
    var topRatedResults: [WineResult] {
        results.sorted { ($0.rating ?? 0) > ($1.rating ?? 0) }
    }

    /// Returns the top 3 rated wines (for emphasis in UI)
    var topThree: [WineResult] {
        Array(topRatedResults.prefix(3))
    }

    /// Check if a wine result is in the top 3
    func isTopThree(_ wine: WineResult) -> Bool {
        topThree.contains(wine)
    }

    /// Returns visible results (confidence >= visibility threshold), deduplicated by ID
    var visibleResults: [WineResult] {
        var seen = Set<String>()
        return results.filter { wine in
            guard OverlayMath.isVisible(confidence: wine.confidence) else { return false }
            guard !seen.contains(wine.id) else { return false }
            seen.insert(wine.id)
            return true
        }
    }

    /// Returns tappable results (confidence >= tappable threshold)
    var tappableResults: [WineResult] {
        results.filter { OverlayMath.isTappable(confidence: $0.confidence) }
    }

    /// Whether partial detection occurred (some in fallback)
    var isPartialDetection: Bool {
        !results.isEmpty && !fallbackList.isEmpty
    }

    /// Whether detection completely failed (fallback only)
    var isFullFailure: Bool {
        results.isEmpty && !fallbackList.isEmpty
    }
}

extension WineResult {
    /// Whether this wine should be tappable for detail sheet
    var isTappable: Bool {
        OverlayMath.isTappable(confidence: confidence)
    }

    /// Confidence label for detail sheet
    var confidenceLabel: String {
        OverlayMath.confidenceLabel(confidence: confidence)
    }
}
