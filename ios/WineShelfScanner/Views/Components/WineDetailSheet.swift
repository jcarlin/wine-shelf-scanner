import SwiftUI

/// Detail sheet shown when tapping a wine rating badge
///
/// Content (max):
/// - Wine name (headline)
/// - Star rating (large)
/// - Confidence label ("Widely rated" / "Limited data")
///
/// Rules:
/// - No scrolling if possible
/// - Swipe down to dismiss
/// - Must feel fast and lightweight
struct WineDetailSheet: View {
    let wine: WineResult

    var body: some View {
        VStack(spacing: 16) {
            // Drag indicator
            Capsule()
                .fill(Color.gray.opacity(0.5))
                .frame(width: 36, height: 4)
                .padding(.top, 8)

            // Wine name
            Text(wine.wineName)
                .font(.title2)
                .fontWeight(.semibold)
                .multilineTextAlignment(.center)
                .foregroundColor(.primary)
                .padding(.horizontal)
                .accessibilityIdentifier("detailSheetWineName")

            // Star rating
            HStack(spacing: 8) {
                ForEach(0..<5, id: \.self) { index in
                    starImage(for: index)
                        .font(.title)
                        .foregroundColor(.yellow)
                }
            }

            // Rating number
            Text(wine.rating.map { String(format: "%.1f", $0) } ?? "No rating")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(.primary)
                .accessibilityIdentifier("detailSheetRating")

            // Confidence label
            Text(wine.confidenceLabel)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.gray.opacity(0.2))
                .cornerRadius(12)
                .accessibilityIdentifier("detailSheetConfidenceLabel")

            Spacer()
        }
        .padding()
        .accessibilityIdentifier("wineDetailSheet")
    }

    @ViewBuilder
    private func starImage(for index: Int) -> some View {
        let ratingValue = wine.rating ?? 0
        let filled = Double(index) + 1 <= ratingValue
        let halfFilled = Double(index) + 0.5 <= ratingValue && Double(index) + 1 > ratingValue

        if filled {
            Image(systemName: "star.fill")
        } else if halfFilled {
            Image(systemName: "star.leadinghalf.filled")
        } else {
            Image(systemName: "star")
        }
    }
}

#Preview("High Confidence") {
    WineDetailSheet(wine: WineResult(
        wineName: "Opus One Napa Valley",
        rating: 4.8,
        confidence: 0.92,
        bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3)
    ))
}

#Preview("Medium Confidence") {
    WineDetailSheet(wine: WineResult(
        wineName: "La Crema Sonoma Coast Pinot Noir",
        rating: 4.1,
        confidence: 0.72,
        bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3)
    ))
}

#Preview("Low Rating") {
    WineDetailSheet(wine: WineResult(
        wineName: "Budget Wine Selection",
        rating: 2.5,
        confidence: 0.85,
        bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3)
    ))
}
