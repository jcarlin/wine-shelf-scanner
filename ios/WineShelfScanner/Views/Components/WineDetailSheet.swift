import SwiftUI

/// Detail sheet shown when tapping a wine rating badge
///
/// Content (max):
/// - Wine type badge (colored by type)
/// - Wine name (headline)
/// - Brand/winery line
/// - Star rating (large)
/// - Review count
/// - Confidence label ("Widely rated" / "Limited data")
/// - Region & varietal
/// - Blurb/description
/// - Review snippets
/// - Feedback buttons (thumbs up/down)
///
/// Rules:
/// - Swipe down to dismiss
/// - Must feel fast and lightweight
struct WineDetailSheet: View {
    let wine: WineResult
    let imageId: String
    var shelfRank: Int? = nil
    var shelfTotal: Int? = nil

    @State private var feedbackState: FeedbackState = .none
    @State private var showCorrectionField = false
    @State private var correctionText = ""
    @State private var isSubmitting = false

    private let feedbackService = FeedbackService()
    private let memoryStore = WineMemoryStore.shared

    /// Wine type to display color mapping
    private let wineTypeColors: [String: Color] = [
        "Red": Color(red: 0.55, green: 0, blue: 0),
        "White": Color(red: 0.96, green: 0.87, blue: 0.70),
        "Rosé": Color(red: 1, green: 0.71, blue: 0.76),
        "Sparkling": Color(red: 1, green: 0.84, blue: 0),
        "Dessert": Color(red: 0.85, green: 0.65, blue: 0.13),
        "Fortified": Color(red: 0.55, green: 0.27, blue: 0.07)
    ]

    /// Wine types that need dark text
    private let darkTextTypes = ["White", "Sparkling", "Rosé"]

    /// Whether this wine has extended metadata
    private var hasMetadata: Bool {
        wine.wineType != nil || wine.brand != nil || wine.region != nil || wine.varietal != nil || wine.blurb != nil
    }

    /// Whether this wine has review info
    private var hasReviews: Bool {
        (wine.reviewCount ?? 0) > 0 || (wine.reviewSnippets?.isEmpty == false)
    }

    enum FeedbackState {
        case none
        case correct
        case incorrect
        case submitted
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Drag indicator
                Capsule()
                    .fill(Color.gray.opacity(0.5))
                    .frame(width: 36, height: 4)
                    .padding(.top, 8)

                // Wine type badge
                if let wineType = wine.wineType {
                    Text(wineType.uppercased())
                        .font(.caption)
                        .fontWeight(.semibold)
                        .tracking(1)
                        .foregroundColor(darkTextTypes.contains(wineType) ? Color(white: 0.2) : .white)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 4)
                        .background(wineTypeColors[wineType] ?? .purple)
                        .cornerRadius(8)
                }

                // Wine name
                Text(wine.wineName)
                    .font(.title2)
                    .fontWeight(.semibold)
                    .multilineTextAlignment(.center)
                    .foregroundColor(.primary)
                    .padding(.horizontal)
                    .accessibilityIdentifier("detailSheetWineName")

                // Brand/winery
                if let brand = wine.brand {
                    Text("by \(brand)")
                        .font(.subheadline)
                        .italic()
                        .foregroundColor(.secondary)
                }

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

                // Review count
                if let reviewCount = wine.reviewCount, reviewCount > 0 {
                    Text(formatReviewCount(reviewCount))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                // Trust signals - rating source breakdown
                if FeatureFlags.shared.trustSignals, let sources = wine.ratingSources, !sources.isEmpty {
                    VStack(spacing: 4) {
                        ForEach(sources.indices, id: \.self) { index in
                            HStack(spacing: 4) {
                                Text(sources[index].displayName)
                                    .font(.caption)
                                    .fontWeight(.medium)
                                    .foregroundColor(.secondary)
                                Text("\(String(format: "%.0f", sources[index].originalRating)) \(sources[index].scaleLabel)")
                                    .font(.caption)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.primary)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.blue.opacity(0.08))
                    .cornerRadius(10)
                    .accessibilityIdentifier("trustSignals")
                } else {
                    // Fallback confidence label
                    Text(wine.confidenceLabel)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.gray.opacity(0.2))
                        .cornerRadius(12)
                        .accessibilityIdentifier("detailSheetConfidenceLabel")
                }

                // Safe pick badge
                if FeatureFlags.shared.safePick && wine.isSafePick == true {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark.shield.fill")
                            .foregroundColor(.green)
                        Text("Crowd favorite")
                            .font(.subheadline)
                            .fontWeight(.medium)
                            .foregroundColor(.green)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.green.opacity(0.1))
                    .cornerRadius(12)
                }

                // Shelf ranking
                if FeatureFlags.shared.shelfRanking, let rank = shelfRank, let total = shelfTotal {
                    Group {
                        if rank == 1 {
                            Text("Best on this shelf")
                                .foregroundColor(Color.yellow)
                        } else {
                            Text("Ranked #\(rank) of \(total) on this shelf")
                                .foregroundColor(.secondary)
                        }
                    }
                    .font(.subheadline)
                    .fontWeight(.medium)
                }

                // Divider
                if hasMetadata || hasReviews {
                    Divider()
                        .frame(width: 200)
                        .padding(.vertical, 8)
                }

                // Region & Varietal
                if wine.region != nil || wine.varietal != nil {
                    HStack(spacing: 32) {
                        if let region = wine.region {
                            VStack(spacing: 2) {
                                Text("REGION")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .tracking(0.5)
                                Text(region)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                                    .foregroundColor(.primary)
                            }
                        }
                        if let varietal = wine.varietal {
                            VStack(spacing: 2) {
                                Text("VARIETAL")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .tracking(0.5)
                                Text(varietal)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                                    .foregroundColor(.primary)
                            }
                        }
                    }
                    .padding(.bottom, 8)
                }

                // Blurb/description
                if let blurb = wine.blurb {
                    Text("\"\(blurb)\"")
                        .font(.subheadline)
                        .italic()
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .background(Color.gray.opacity(0.1))
                        .cornerRadius(12)
                }

                // Food pairing
                if FeatureFlags.shared.pairings, let pairing = wine.pairing {
                    HStack(spacing: 8) {
                        Image(systemName: "fork.knife")
                            .font(.subheadline)
                            .foregroundColor(Color(red: 0.8, green: 0.6, blue: 0.2))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Goes with")
                                .font(.caption)
                                .foregroundColor(.secondary)
                            Text(pairing)
                                .font(.subheadline)
                                .foregroundColor(.primary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color(red: 0.98, green: 0.96, blue: 0.90))
                    .cornerRadius(12)
                }

                // Review snippets
                if let snippets = wine.reviewSnippets, !snippets.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("What people say")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundColor(.primary)

                        ForEach(snippets.indices, id: \.self) { index in
                            HStack(alignment: .top, spacing: 8) {
                                Rectangle()
                                    .fill(Color.yellow)
                                    .frame(width: 3)
                                Text("\"\(snippets[index])\"")
                                    .font(.caption)
                                    .italic()
                                    .foregroundColor(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .padding(.vertical, 4)
                            .padding(.horizontal, 8)
                            .background(Color.gray.opacity(0.05))
                            .cornerRadius(4)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                }

                // Wine memory banner
                if FeatureFlags.shared.wineMemory {
                    memoryBanner
                }

                // Share button
                if FeatureFlags.shared.share {
                    Button {
                        shareWine()
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "square.and.arrow.up")
                                .font(.subheadline)
                            Text("Share this pick")
                                .font(.subheadline)
                                .fontWeight(.medium)
                        }
                        .foregroundColor(.blue)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(Color.blue.opacity(0.1))
                        .cornerRadius(12)
                    }
                    .accessibilityIdentifier("shareButton")
                }

                // Feedback section
                feedbackSection

                Spacer(minLength: 16)
            }
            .padding()
        }
        .accessibilityIdentifier("wineDetailSheet")
    }

    /// Format review count (e.g., 12500 -> "12.5K reviews")
    private func formatReviewCount(_ count: Int) -> String {
        if count >= 1000 {
            let formatted = Double(count) / 1000.0
            let text = String(format: "%.1f", formatted).replacingOccurrences(of: ".0", with: "")
            return "\(text)K reviews"
        }
        return "\(count) reviews"
    }

    @ViewBuilder
    private var memoryBanner: some View {
        if let sentiment = memoryStore.get(wineName: wine.wineName) {
            HStack(spacing: 6) {
                if sentiment == .liked {
                    Image(systemName: "heart.fill")
                        .foregroundColor(.green)
                        .font(.caption)
                    Text("You liked this wine")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                } else {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.red)
                        .font(.caption)
                    Text("You didn't like this wine")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button("Undo") {
                    memoryStore.clear(wineName: wine.wineName)
                }
                .font(.caption)
                .foregroundColor(.blue)
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(sentiment == .liked
                        ? Color.green.opacity(0.1)
                        : Color.red.opacity(0.1))
            )
            .accessibilityIdentifier("wineMemoryBanner")
        }
    }

    @ViewBuilder
    private var feedbackSection: some View {
        VStack(spacing: 12) {
            if feedbackState == .submitted {
                // Thank you message
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("Thanks for your feedback!")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .accessibilityIdentifier("feedbackConfirmation")
                .transition(.opacity)
            } else if showCorrectionField {
                // Correction input
                VStack(spacing: 8) {
                    Text("What's the correct wine?")
                        .font(.subheadline)
                        .foregroundColor(.secondary)

                    TextField("Wine name", text: $correctionText)
                        .textFieldStyle(.roundedBorder)
                        .padding(.horizontal)
                        .accessibilityIdentifier("correctionTextField")

                    HStack(spacing: 12) {
                        Button("Cancel") {
                            withAnimation {
                                showCorrectionField = false
                                correctionText = ""
                            }
                        }
                        .foregroundColor(.secondary)

                        Button("Submit") {
                            submitFeedback(isCorrect: false, correctedName: correctionText)
                        }
                        .disabled(isSubmitting)
                        .foregroundColor(.blue)
                    }
                    .font(.subheadline)
                }
                .transition(.opacity)
            } else {
                // Feedback prompt
                VStack(spacing: 8) {
                    Text("Is this the right wine?")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .accessibilityIdentifier("feedbackPrompt")

                    HStack(spacing: 24) {
                        // Thumbs up
                        Button {
                            submitFeedback(isCorrect: true)
                        } label: {
                            VStack(spacing: 4) {
                                Image(systemName: feedbackState == .correct ? "hand.thumbsup.fill" : "hand.thumbsup")
                                    .font(.title2)
                                Text("Yes")
                                    .font(.caption)
                            }
                        }
                        .foregroundColor(feedbackState == .correct ? .green : .primary)
                        .disabled(isSubmitting)
                        .accessibilityIdentifier("thumbsUpButton")

                        // Thumbs down
                        Button {
                            withAnimation {
                                showCorrectionField = true
                            }
                        } label: {
                            VStack(spacing: 4) {
                                Image(systemName: feedbackState == .incorrect ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                                    .font(.title2)
                                Text("No")
                                    .font(.caption)
                            }
                        }
                        .foregroundColor(feedbackState == .incorrect ? .red : .primary)
                        .disabled(isSubmitting)
                        .accessibilityIdentifier("thumbsDownButton")
                    }
                }
            }
        }
        .padding(.top, 8)
        .animation(.easeInOut(duration: 0.2), value: feedbackState)
        .animation(.easeInOut(duration: 0.2), value: showCorrectionField)
    }

    private func submitFeedback(isCorrect: Bool, correctedName: String? = nil) {
        isSubmitting = true
        feedbackState = isCorrect ? .correct : .incorrect

        // Save to local wine memory
        if FeatureFlags.shared.wineMemory {
            memoryStore.save(
                wineName: wine.wineName,
                sentiment: isCorrect ? .liked : .disliked
            )
        }

        Task {
            do {
                try await feedbackService.submitFeedback(
                    imageId: imageId,
                    wineName: wine.wineName,
                    isCorrect: isCorrect,
                    correctedName: correctedName?.isEmpty == true ? nil : correctedName
                )

                await MainActor.run {
                    withAnimation {
                        feedbackState = .submitted
                        showCorrectionField = false
                    }
                }
            } catch {
                // Silently fail - feedback is best-effort
                #if DEBUG
                print("Feedback error: \(error)")
                #endif

                await MainActor.run {
                    // Still show success to user (feedback is fire-and-forget)
                    withAnimation {
                        feedbackState = .submitted
                        showCorrectionField = false
                    }
                }
            }

            await MainActor.run {
                isSubmitting = false
            }
        }
    }

    private func shareWine() {
        var text = "\(wine.wineName)"
        if let rating = wine.rating {
            text += " - \(String(format: "%.1f", rating)) stars"
        }
        if let brand = wine.brand {
            text += " by \(brand)"
        }
        if let region = wine.region {
            text += " (\(region))"
        }
        text += "\n\nFound with Wine Shelf Scanner"

        let activityVC = UIActivityViewController(activityItems: [text], applicationActivities: nil)
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let root = windowScene.windows.first?.rootViewController {
            // Handle iPad popover
            if let popover = activityVC.popoverPresentationController {
                popover.sourceView = root.view
                popover.sourceRect = CGRect(x: root.view.bounds.midX, y: root.view.bounds.midY, width: 0, height: 0)
                popover.permittedArrowDirections = []
            }
            root.present(activityVC, animated: true)
        }
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

#Preview("High Confidence with Metadata") {
    WineDetailSheet(
        wine: WineResult(
            wineName: "Opus One Napa Valley",
            rating: 4.8,
            confidence: 0.92,
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3),
            wineType: "Red",
            brand: "Opus One Winery",
            region: "Napa Valley",
            varietal: "Cabernet Sauvignon Blend",
            blurb: "A legendary Napa Valley wine known for its elegance and complexity.",
            reviewCount: 12500,
            reviewSnippets: ["Exceptional balance and finesse", "Worth every penny"]
        ),
        imageId: "preview-123"
    )
}

#Preview("Medium Confidence") {
    WineDetailSheet(
        wine: WineResult(
            wineName: "La Crema Sonoma Coast Pinot Noir",
            rating: 4.1,
            confidence: 0.72,
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3),
            wineType: "Red",
            brand: "La Crema",
            region: "Sonoma Coast",
            varietal: "Pinot Noir",
            blurb: nil,
            reviewCount: nil,
            reviewSnippets: nil
        ),
        imageId: "preview-123"
    )
}

#Preview("Minimal Data") {
    WineDetailSheet(
        wine: WineResult(
            wineName: "Budget Wine Selection",
            rating: 2.5,
            confidence: 0.85,
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3),
            wineType: nil,
            brand: nil,
            region: nil,
            varietal: nil,
            blurb: nil,
            reviewCount: nil,
            reviewSnippets: nil
        ),
        imageId: "preview-123"
    )
}

#Preview("White Wine") {
    WineDetailSheet(
        wine: WineResult(
            wineName: "Cloudy Bay Sauvignon Blanc",
            rating: 4.3,
            confidence: 0.88,
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3),
            wineType: "White",
            brand: "Cloudy Bay",
            region: "Marlborough",
            varietal: "Sauvignon Blanc",
            blurb: "Crisp and refreshing with tropical fruit notes.",
            reviewCount: 8200,
            reviewSnippets: nil
        ),
        imageId: "preview-123"
    )
}
