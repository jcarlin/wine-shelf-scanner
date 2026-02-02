import SwiftUI

/// Detail sheet shown when tapping a wine rating badge
///
/// Content (max):
/// - Wine name (headline)
/// - Star rating (large)
/// - Confidence label ("Widely rated" / "Limited data")
/// - Feedback buttons (thumbs up/down)
///
/// Rules:
/// - No scrolling if possible
/// - Swipe down to dismiss
/// - Must feel fast and lightweight
struct WineDetailSheet: View {
    let wine: WineResult
    let imageId: String

    @State private var feedbackState: FeedbackState = .none
    @State private var showCorrectionField = false
    @State private var correctionText = ""
    @State private var isSubmitting = false

    private let feedbackService = FeedbackService()

    enum FeedbackState {
        case none
        case correct
        case incorrect
        case submitted
    }

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

            // Feedback section
            feedbackSection

            Spacer()
        }
        .padding()
        .accessibilityIdentifier("wineDetailSheet")
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
    WineDetailSheet(
        wine: WineResult(
            wineName: "Opus One Napa Valley",
            rating: 4.8,
            confidence: 0.92,
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3)
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
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3)
        ),
        imageId: "preview-123"
    )
}

#Preview("Low Rating") {
    WineDetailSheet(
        wine: WineResult(
            wineName: "Budget Wine Selection",
            rating: 2.5,
            confidence: 0.85,
            bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.3)
        ),
        imageId: "preview-123"
    )
}
