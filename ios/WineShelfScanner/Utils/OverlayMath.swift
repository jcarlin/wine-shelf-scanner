import SwiftUI

/// Centralized overlay placement math
/// All calculations for positioning rating badges on wine bottles
struct OverlayMath {

    // MARK: - Image Bounds Calculation

    /// Calculate actual image bounds within container when using .fit content mode
    ///
    /// When using aspectRatio(contentMode: .fit), the image scales to fit while
    /// maintaining aspect ratio, potentially creating letterbox areas.
    ///
    /// - Parameters:
    ///   - imageSize: Original image dimensions
    ///   - containerSize: Container dimensions
    /// - Returns: Rectangle describing where the image renders within the container
    static func getImageBounds(imageSize: CGSize, containerSize: CGSize) -> CGRect {
        let imageAspect = imageSize.width / imageSize.height
        let containerAspect = containerSize.width / containerSize.height

        if imageAspect > containerAspect {
            // Image is wider than container - letterbox top/bottom
            let scaledHeight = containerSize.width / imageAspect
            let y = (containerSize.height - scaledHeight) / 2
            return CGRect(x: 0, y: y, width: containerSize.width, height: scaledHeight)
        } else {
            // Image is taller than container - letterbox left/right
            let scaledWidth = containerSize.height * imageAspect
            let x = (containerSize.width - scaledWidth) / 2
            return CGRect(x: x, y: 0, width: scaledWidth, height: containerSize.height)
        }
    }

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

    /// Confidence-based opacity for badges (dimmed base values)
    /// | Confidence | Opacity |
    /// |------------|---------|
    /// | >= 0.85    | 0.85    |
    /// | 0.65-0.85  | 0.60    |
    /// | 0.45-0.65  | 0.35    |
    /// | < 0.45     | 0.0     |
    static func opacity(confidence: Double) -> Double {
        switch confidence {
        case 0.85...1.0:
            return 0.85
        case 0.65..<0.85:
            return 0.60
        case 0.45..<0.65:
            return 0.35
        default:
            return 0.0
        }
    }

    /// Opacity with visual emphasis: top-3 wines get boosted, #1 gets extra boost, non-top-3 are dimmed
    static func opacity(confidence: Double, isTopThree: Bool, isBestPick: Bool = false, visualEmphasis: Bool) -> Double {
        let baseOpacity = opacity(confidence: confidence)
        if !visualEmphasis || baseOpacity == 0 { return baseOpacity }
        if isBestPick { return min(baseOpacity + 0.35, 1.0) }
        if isTopThree { return min(baseOpacity + 0.25, 1.0) }
        return baseOpacity * 0.65
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

    /// Confidence label for detail sheet ("Widely rated" for high confidence, nil otherwise)
    static func confidenceLabel(confidence: Double) -> String? {
        confidence >= highConfidenceThreshold
            ? NSLocalizedString("detail.widelyRated", comment: "High confidence label")
            : nil
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

    // MARK: - Corner Brackets

    /// A single line segment for a corner bracket
    struct CornerBracketLine {
        let x1: CGFloat
        let y1: CGFloat
        let x2: CGFloat
        let y2: CGFloat
    }

    /// Corner bracket configuration
    private static let bracketArmFraction: CGFloat = 0.18
    private static let bracketMinArm: CGFloat = 8
    private static let bracketMaxArm: CGFloat = 40

    /// Compute 8 line segments (2 per corner) forming "L"-shaped corner brackets
    /// around a bounding box.
    /// - Parameters:
    ///   - bbox: Normalized bounding box (0-1)
    ///   - geo: Container size in points
    /// - Returns: Array of 8 line segments in point coordinates
    static func cornerBrackets(bbox: CGRect, geo: CGSize) -> [CornerBracketLine] {
        let left = bbox.origin.x * geo.width
        let top = bbox.origin.y * geo.height
        let right = (bbox.origin.x + bbox.size.width) * geo.width
        let bottom = (bbox.origin.y + bbox.size.height) * geo.height

        let armH = min(max(bbox.size.width * geo.width * bracketArmFraction, bracketMinArm), bracketMaxArm)
        let armV = min(max(bbox.size.height * geo.height * bracketArmFraction, bracketMinArm), bracketMaxArm)

        return [
            // Top-left
            CornerBracketLine(x1: left, y1: top, x2: left + armH, y2: top),
            CornerBracketLine(x1: left, y1: top, x2: left, y2: top + armV),
            // Top-right
            CornerBracketLine(x1: right, y1: top, x2: right - armH, y2: top),
            CornerBracketLine(x1: right, y1: top, x2: right, y2: top + armV),
            // Bottom-left
            CornerBracketLine(x1: left, y1: bottom, x2: left + armH, y2: bottom),
            CornerBracketLine(x1: left, y1: bottom, x2: left, y2: bottom - armV),
            // Bottom-right
            CornerBracketLine(x1: right, y1: bottom, x2: right - armH, y2: bottom),
            CornerBracketLine(x1: right, y1: bottom, x2: right, y2: bottom - armV),
        ]
    }

    /// Compute corner brackets from BoundingBox model
    static func cornerBrackets(bbox: BoundingBox, geo: CGSize) -> [CornerBracketLine] {
        cornerBrackets(bbox: bbox.cgRect, geo: geo)
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
