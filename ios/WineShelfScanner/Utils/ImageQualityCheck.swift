import UIKit

/// Pre-upload image quality heuristics.
///
/// Megapixels only proxy the real signal (bottle width in pixels), so this
/// check is advisory — the user can always choose to scan anyway.
enum ImageQualityCheck {
    /// Below ~2 megapixels, wine labels are unlikely to be readable.
    static let minimumPixelCount = 2_000_000

    /// Whether the given pixel dimensions fall below the recommended resolution.
    static func isBelowRecommendedResolution(pixelWidth: Int, pixelHeight: Int) -> Bool {
        pixelWidth * pixelHeight < minimumPixelCount
    }

    /// Whether an image falls below the recommended resolution (points × scale).
    static func isBelowRecommendedResolution(_ image: UIImage) -> Bool {
        let pixelWidth = Int((image.size.width * image.scale).rounded())
        let pixelHeight = Int((image.size.height * image.scale).rounded())
        return isBelowRecommendedResolution(pixelWidth: pixelWidth, pixelHeight: pixelHeight)
    }
}
