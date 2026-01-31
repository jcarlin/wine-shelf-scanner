import Foundation
import CoreGraphics

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

    enum CodingKeys: String, CodingKey {
        case imageId = "image_id"
        case results
        case fallbackList = "fallback_list"
    }
}

/// A detected wine bottle with rating and position
struct WineResult: Codable, Equatable, Identifiable {
    let wineName: String
    let rating: Double
    let confidence: Double
    let bbox: BoundingBox

    var id: String { wineName }

    enum CodingKeys: String, CodingKey {
        case wineName = "wine_name"
        case rating
        case confidence
        case bbox
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
    let rating: Double

    var id: String { wineName }

    enum CodingKeys: String, CodingKey {
        case wineName = "wine_name"
        case rating
    }
}

// MARK: - Convenience Extensions

extension ScanResponse {
    /// Returns wines sorted by rating (highest first)
    var topRatedResults: [WineResult] {
        results.sorted { $0.rating > $1.rating }
    }

    /// Returns the top 3 rated wines (for emphasis in UI)
    var topThree: [WineResult] {
        Array(topRatedResults.prefix(3))
    }

    /// Check if a wine result is in the top 3
    func isTopThree(_ wine: WineResult) -> Bool {
        topThree.contains(wine)
    }

    /// Returns visible results (confidence >= visibility threshold)
    var visibleResults: [WineResult] {
        results.filter { OverlayMath.isVisible(confidence: $0.confidence) }
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
