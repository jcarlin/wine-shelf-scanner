import SwiftUI

/// Centralized overlay placement math
/// All calculations for positioning rating badges on wine bottles
struct OverlayMath {

    // MARK: - Anchor Point Calculation

    /// Calculate the anchor point for a rating badge
    /// - Parameters:
    ///   - bbox: Normalized bounding box (0-1)
    ///   - geo: Container size
    /// - Returns: Screen position for badge center
    static func anchorPoint(bbox: CGRect, geo: CGSize) -> CGPoint {
        // Anchor at horizontal center, vertical 25% from top
        let x = (bbox.origin.x + bbox.size.width / 2) * geo.width
        let y = (bbox.origin.y + bbox.size.height * 0.25) * geo.height
        return CGPoint(x: x, y: y)
    }

    /// Calculate anchor point from BoundingBox model
    static func anchorPoint(bbox: BoundingBox, geo: CGSize) -> CGPoint {
        anchorPoint(bbox: bbox.cgRect, geo: geo)
    }

    // MARK: - Opacity

    /// Confidence-based opacity for badges
    /// | Confidence | Opacity |
    /// |------------|---------|
    /// | >= 0.85    | 1.0     |
    /// | 0.65-0.85  | 0.75    |
    /// | 0.45-0.65  | 0.5     |
    /// | < 0.45     | 0.0     |
    static func opacity(confidence: Double) -> Double {
        switch confidence {
        case 0.85...1.0:
            return 1.0
        case 0.65..<0.85:
            return 0.75
        case 0.45..<0.65:
            return 0.5
        default:
            return 0.0
        }
    }

    // MARK: - Confidence Thresholds

    /// Minimum confidence to show overlay (opacity 0.5)
    static let visibilityThreshold = 0.45

    /// Minimum confidence for tappable overlays (opacity 0.75)
    static let tappableThreshold = 0.65

    /// Minimum confidence for "Widely rated" label (opacity 1.0)
    static let highConfidenceThreshold = 0.85

    // MARK: - Visibility

    /// Whether a wine should be visible (confidence >= 0.45)
    static func isVisible(confidence: Double) -> Bool {
        confidence >= visibilityThreshold
    }

    /// Whether a wine should be tappable (confidence >= 0.65)
    static func isTappable(confidence: Double) -> Bool {
        confidence >= tappableThreshold
    }

    /// Confidence label for detail sheet ("Widely rated" or "Limited data")
    static func confidenceLabel(confidence: Double) -> String {
        confidence >= highConfidenceThreshold ? "Widely rated" : "Limited data"
    }

    // MARK: - Collision Avoidance

    /// Adjust anchor point to avoid collisions
    /// - Parameters:
    ///   - point: Original anchor point
    ///   - bbox: Bounding box for the bottle
    ///   - geo: Container size
    ///   - badgeSize: Size of the rating badge
    /// - Returns: Adjusted point clamped to image bounds
    static func adjustedAnchorPoint(
        _ point: CGPoint,
        bbox: CGRect,
        geo: CGSize,
        badgeSize: CGSize
    ) -> CGPoint {
        var adjusted = point

        // If bbox height is small (partial bottle), anchor higher
        if bbox.height < 0.15 {
            adjusted.y = bbox.origin.y * geo.height + badgeSize.height / 2 + 4
        }

        // Clamp to image bounds with padding
        let padding: CGFloat = 4
        adjusted.x = max(badgeSize.width / 2 + padding, min(adjusted.x, geo.width - badgeSize.width / 2 - padding))
        adjusted.y = max(badgeSize.height / 2 + padding, min(adjusted.y, geo.height - badgeSize.height / 2 - padding))

        return adjusted
    }

    // MARK: - Badge Sizing

    /// Base badge size
    static let baseBadgeSize = CGSize(width: 44, height: 24)

    /// Top-3 badge size (larger)
    static let topThreeBadgeSize = CGSize(width: 52, height: 28)

    /// Get badge size based on whether it's in top 3
    static func badgeSize(isTopThree: Bool) -> CGSize {
        isTopThree ? topThreeBadgeSize : baseBadgeSize
    }
}
