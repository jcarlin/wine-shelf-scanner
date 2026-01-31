import SwiftUI

/// Rating badge component displayed on wine bottles
///
/// Specs:
/// - Base size: 44x24pt
/// - Top-3 size: 52x28pt
/// - Background: #000000 @ 70%
/// - Text: White, SF Pro Rounded Bold
/// - Drop shadow: 2pt blur
struct RatingBadge: View {
    let rating: Double
    let confidence: Double
    let isTopThree: Bool
    let isTappable: Bool

    private var badgeSize: CGSize {
        OverlayMath.badgeSize(isTopThree: isTopThree)
    }

    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: "star.fill")
                .font(.system(size: isTopThree ? 12 : 10))
                .foregroundColor(.yellow)

            Text(String(format: "%.1f", rating))
                .font(.system(
                    size: isTopThree ? 14 : 12,
                    weight: .bold,
                    design: .rounded
                ))
                .foregroundColor(.white)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .frame(minWidth: badgeSize.width, minHeight: badgeSize.height)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.black.opacity(0.7))
        )
        .overlay(
            // Top-3 glow effect
            RoundedRectangle(cornerRadius: 6)
                .stroke(
                    isTopThree ? Color.yellow.opacity(0.6) : Color.clear,
                    lineWidth: isTopThree ? 2 : 0
                )
        )
        .shadow(color: .black.opacity(0.5), radius: 2, x: 0, y: 1)
        .contentShape(Rectangle()) // Make entire badge tappable
    }
}

#Preview("Top 3") {
    VStack(spacing: 20) {
        RatingBadge(rating: 4.8, confidence: 0.95, isTopThree: true, isTappable: true)
        RatingBadge(rating: 4.5, confidence: 0.88, isTopThree: true, isTappable: true)
        RatingBadge(rating: 4.3, confidence: 0.82, isTopThree: true, isTappable: true)
    }
    .padding()
    .background(Color.gray)
}

#Preview("Normal") {
    VStack(spacing: 20) {
        RatingBadge(rating: 4.1, confidence: 0.75, isTopThree: false, isTappable: true)
        RatingBadge(rating: 3.8, confidence: 0.68, isTopThree: false, isTappable: true)
        RatingBadge(rating: 3.5, confidence: 0.52, isTopThree: false, isTappable: false)
    }
    .padding()
    .background(Color.gray)
}

#Preview("All Confidence Levels") {
    VStack(spacing: 20) {
        // High confidence (1.0 opacity)
        RatingBadge(rating: 4.5, confidence: 0.92, isTopThree: false, isTappable: true)
            .opacity(OverlayMath.opacity(confidence: 0.92))

        // Medium confidence (0.75 opacity)
        RatingBadge(rating: 4.0, confidence: 0.75, isTopThree: false, isTappable: true)
            .opacity(OverlayMath.opacity(confidence: 0.75))

        // Low confidence (0.5 opacity)
        RatingBadge(rating: 3.5, confidence: 0.55, isTopThree: false, isTappable: false)
            .opacity(OverlayMath.opacity(confidence: 0.55))

        // Very low confidence (hidden)
        RatingBadge(rating: 3.0, confidence: 0.40, isTopThree: false, isTappable: false)
            .opacity(OverlayMath.opacity(confidence: 0.40))
    }
    .padding()
    .background(Color.gray)
}
