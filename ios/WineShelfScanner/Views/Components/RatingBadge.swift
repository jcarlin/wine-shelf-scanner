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
    let rating: Double?
    let confidence: Double
    let isTopThree: Bool
    let isTappable: Bool
    let wineName: String
    var shelfRank: Int? = nil
    var isSafePick: Bool = false
    var userSentiment: WineSentiment? = nil

    private var badgeSize: CGSize {
        OverlayMath.badgeSize(isTopThree: isTopThree)
    }

    /// Sanitized wine name for accessibility identifier
    private var sanitizedWineName: String {
        wineName.lowercased()
            .replacingOccurrences(of: " ", with: "-")
            .replacingOccurrences(of: "'", with: "")
    }

    /// Color for rank number
    private var rankColor: Color {
        guard let rank = shelfRank else { return .white }
        switch rank {
        case 1: return Color.yellow
        case 2: return Color(white: 0.85)
        default: return Color(white: 0.7)
        }
    }

    /// Whether this is the #1 ranked wine and visual emphasis is on
    private var isBestPick: Bool {
        FeatureFlags.shared.visualEmphasis && shelfRank == 1
    }

    var body: some View {
        VStack(spacing: 2) {
            // "Best Pick" label above #1 badge
            if isBestPick {
                Text("BEST PICK")
                    .font(.system(size: 8, weight: .heavy, design: .rounded))
                    .tracking(0.5)
                    .foregroundColor(Color.yellow)
                    .shadow(color: .black.opacity(0.8), radius: 1, x: 0, y: 1)
            }

            HStack(spacing: 2) {
                Image(systemName: "star.fill")
                    .font(.system(size: isTopThree ? 12 : 10))
                    .foregroundColor(.yellow)

                Text(rating.map { String(format: "%.1f", $0) } ?? "—")
                    .font(.system(
                        size: isTopThree ? 14 : 12,
                        weight: .bold,
                        design: .rounded
                    ))
                    .foregroundColor(.white)

                // Safe pick shield icon
                if isSafePick {
                    Image(systemName: "checkmark.shield.fill")
                        .font(.system(size: 9))
                        .foregroundColor(.green)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .frame(minWidth: badgeSize.width, minHeight: badgeSize.height)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.black.opacity(0.85))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(
                        isTopThree ? Color.yellow.opacity(isBestPick ? 0.9 : 0.6) : Color.clear,
                        lineWidth: isTopThree ? (isBestPick ? 2.5 : 2) : 0
                    )
            )
            .shadow(
                color: isBestPick ? Color.yellow.opacity(0.6) : .black.opacity(0.5),
                radius: isBestPick ? 8 : 2,
                x: 0,
                y: isBestPick ? 0 : 1
            )
            .overlay(alignment: .topTrailing) {
                if let sentiment = userSentiment {
                    Group {
                        if sentiment == .disliked {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.red)
                        } else {
                            Image(systemName: "heart.fill")
                                .foregroundColor(.green)
                        }
                    }
                    .font(.system(size: 12))
                    .shadow(color: .black.opacity(0.8), radius: 1, x: 0, y: 0)
                    .offset(x: 6, y: -6)
                }
            }

            // Shelf rank number below badge
            if let rank = shelfRank {
                Text("#\(rank)")
                    .font(.system(size: rank == 1 ? 10 : 9, weight: .bold, design: .rounded))
                    .foregroundColor(rankColor)
                    .shadow(color: .black.opacity(0.8), radius: 1, x: 0, y: 1)
            }
        }
        .contentShape(Rectangle())
        .accessibilityIdentifier("ratingBadge_\(sanitizedWineName)")
    }
}

#Preview("Top 3") {
    VStack(spacing: 20) {
        RatingBadge(rating: 4.8, confidence: 0.95, isTopThree: true, isTappable: true, wineName: "Opus One")
        RatingBadge(rating: 4.5, confidence: 0.88, isTopThree: true, isTappable: true, wineName: "Caymus")
        RatingBadge(rating: 4.3, confidence: 0.82, isTopThree: true, isTappable: true, wineName: "Silver Oak")
    }
    .padding()
    .background(Color.gray)
}

#Preview("Normal") {
    VStack(spacing: 20) {
        RatingBadge(rating: 4.1, confidence: 0.75, isTopThree: false, isTappable: true, wineName: "La Crema")
        RatingBadge(rating: 3.8, confidence: 0.68, isTopThree: false, isTappable: true, wineName: "Meiomi")
        RatingBadge(rating: 3.5, confidence: 0.52, isTopThree: false, isTappable: false, wineName: "Budget Wine")
    }
    .padding()
    .background(Color.gray)
}

#Preview("All Confidence Levels") {
    VStack(spacing: 20) {
        // High confidence (1.0 opacity)
        RatingBadge(rating: 4.5, confidence: 0.92, isTopThree: false, isTappable: true, wineName: "High Conf Wine")
            .opacity(OverlayMath.opacity(confidence: 0.92))

        // Medium confidence (0.75 opacity)
        RatingBadge(rating: 4.0, confidence: 0.75, isTopThree: false, isTappable: true, wineName: "Med Conf Wine")
            .opacity(OverlayMath.opacity(confidence: 0.75))

        // Low confidence (0.5 opacity)
        RatingBadge(rating: 3.5, confidence: 0.55, isTopThree: false, isTappable: false, wineName: "Low Conf Wine")
            .opacity(OverlayMath.opacity(confidence: 0.55))

        // Very low confidence (hidden)
        RatingBadge(rating: 3.0, confidence: 0.40, isTopThree: false, isTappable: false, wineName: "Very Low Wine")
            .opacity(OverlayMath.opacity(confidence: 0.40))
    }
    .padding()
    .background(Color.gray)
}
