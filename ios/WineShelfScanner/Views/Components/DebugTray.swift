import SwiftUI

/// Collapsible debug tray showing pipeline debug info below scan results
struct DebugTray: View {
    let debugData: DebugData
    @State private var isExpanded = false

    var body: some View {
        VStack(spacing: 0) {
            // Header with summary stats
            headerView
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isExpanded.toggle()
                    }
                }

            // Expandable content
            if isExpanded {
                stepsList
            }
        }
        .background(Color.black.opacity(0.95))
        .cornerRadius(isExpanded ? 0 : 12)
        .accessibilityIdentifier("debugTray")
    }

    private var headerView: some View {
        HStack {
            Image(systemName: "wrench.and.screwdriver.fill")
                .foregroundColor(.orange)

            Text("Debug")
                .font(.headline)
                .foregroundColor(.white)

            Spacer()

            // Summary stats
            HStack(spacing: 12) {
                statPill(value: debugData.textsMatched, total: debugData.totalOcrTexts, label: "matched")
                if debugData.llmCallsMade > 0 {
                    statPill(value: debugData.llmCallsMade, label: "LLM")
                }
            }
            .accessibilityIdentifier("debugStatSummary")

            Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                .foregroundColor(.gray)
                .font(.caption)
                .accessibilityIdentifier("debugTrayExpand")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.black.opacity(0.8))
        .accessibilityIdentifier("debugTrayHeader")
    }

    private func statPill(value: Int, total: Int? = nil, label: String) -> some View {
        HStack(spacing: 4) {
            if let total = total {
                Text("\(value)/\(total)")
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.white)
            } else {
                Text("\(value)")
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.white)
            }
            Text(label)
                .font(.caption2)
                .foregroundColor(.gray)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.white.opacity(0.1))
        .cornerRadius(8)
    }

    private var stepsList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(Array(debugData.pipelineSteps.enumerated()), id: \.element.id) { index, step in
                    DebugStepRow(step: step)
                        .accessibilityIdentifier("debugStep_\(index)")
                    Divider()
                        .background(Color.gray.opacity(0.3))
                }
            }
        }
        .frame(maxHeight: 300)
        .accessibilityIdentifier("debugStepsList")
    }
}

/// Individual row for a pipeline debug step
struct DebugStepRow: View {
    let step: DebugPipelineStep
    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Main row
            Button(action: { isExpanded.toggle() }) {
                HStack(alignment: .center, spacing: 12) {
                    statusIcon

                    VStack(alignment: .leading, spacing: 2) {
                        Text(step.normalizedText.isEmpty ? "(empty)" : step.normalizedText)
                            .font(.subheadline)
                            .foregroundColor(.white)
                            .lineLimit(1)

                        if let result = step.finalResult {
                            Text(result.wineName)
                                .font(.caption)
                                .foregroundColor(.green.opacity(0.8))
                                .lineLimit(1)
                        } else if let failure = step.stepFailed {
                            Text("Failed: \(failure)")
                                .font(.caption)
                                .foregroundColor(.red.opacity(0.8))
                        }
                    }

                    Spacer()

                    if let scores = step.fuzzyMatch?.scores {
                        Text(String(format: "%.0f%%", scores.weightedScore * 100))
                            .font(.caption.monospacedDigit())
                            .foregroundColor(.gray)
                    }

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .foregroundColor(.gray)
                        .font(.caption2)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // Expanded detail panel
            if isExpanded {
                detailPanel
            }
        }
        .background(isExpanded ? Color.white.opacity(0.05) : Color.clear)
    }

    private var statusIcon: some View {
        Group {
            switch step.status {
            case .success:
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
            case .warning:
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.yellow)
            case .failure:
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
            }
        }
        .font(.system(size: 16))
    }

    private var detailPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Raw OCR text
            detailSection(title: "Raw OCR", content: step.rawText)

            // Normalized text
            if step.normalizedText != step.rawText {
                detailSection(title: "Normalized", content: step.normalizedText)
            }

            // Fuzzy match scores
            if let fuzzy = step.fuzzyMatch, let scores = fuzzy.scores {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Fuzzy Match Scores")
                        .font(.caption)
                        .foregroundColor(.gray)

                    if let candidate = fuzzy.candidate {
                        HStack {
                            Text("Candidate:")
                                .font(.caption2)
                                .foregroundColor(.gray)
                            Text(candidate)
                                .font(.caption2)
                                .foregroundColor(.white)
                        }
                    }

                    HStack(spacing: 16) {
                        scoreItem(label: "Ratio", value: scores.ratio)
                        scoreItem(label: "Partial", value: scores.partialRatio)
                        scoreItem(label: "Token", value: scores.tokenSortRatio)
                        scoreItem(label: "Phonetic", value: scores.phoneticBonus)
                    }

                    HStack {
                        Text("Weighted:")
                            .font(.caption2.bold())
                            .foregroundColor(.gray)
                        Text(String(format: "%.2f", scores.weightedScore))
                            .font(.caption2.monospacedDigit().bold())
                            .foregroundColor(scores.weightedScore >= 0.7 ? .green : .orange)
                    }
                }
            }

            // LLM validation
            if let llm = step.llmValidation {
                VStack(alignment: .leading, spacing: 6) {
                    Text("LLM Validation")
                        .font(.caption)
                        .foregroundColor(.gray)

                    HStack {
                        Image(systemName: llm.isValidMatch ? "checkmark.circle" : "xmark.circle")
                            .foregroundColor(llm.isValidMatch ? .green : .red)
                        Text(llm.isValidMatch ? "Match confirmed" : "Match rejected")
                            .font(.caption2)
                            .foregroundColor(.white)
                    }

                    if let wineName = llm.wineName {
                        HStack {
                            Text("Wine:")
                                .font(.caption2)
                                .foregroundColor(.gray)
                            Text(wineName)
                                .font(.caption2)
                                .foregroundColor(.white)
                        }
                    }

                    Text(llm.reasoning)
                        .font(.caption2)
                        .foregroundColor(.gray)
                        .italic()
                }
            }

            // Final result
            if let result = step.finalResult {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Final Result")
                        .font(.caption)
                        .foregroundColor(.gray)

                    HStack {
                        Text(result.wineName)
                            .font(.caption2.bold())
                            .foregroundColor(.green)
                        Spacer()
                        Text("conf: \(String(format: "%.0f%%", result.confidence * 100))")
                            .font(.caption2.monospacedDigit())
                            .foregroundColor(.gray)
                        Text("src: \(result.source)")
                            .font(.caption2)
                            .foregroundColor(.gray)
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .padding(.leading, 28) // Indent past the status icon
        .background(Color.white.opacity(0.03))
    }

    private func detailSection(title: String, content: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundColor(.gray)
            Text(content.isEmpty ? "(empty)" : content)
                .font(.caption2)
                .foregroundColor(.white.opacity(0.9))
                .lineLimit(3)
        }
    }

    private func scoreItem(label: String, value: Double) -> some View {
        VStack(spacing: 2) {
            Text(String(format: "%.2f", value))
                .font(.caption2.monospacedDigit())
                .foregroundColor(.white)
            Text(label)
                .font(.system(size: 8))
                .foregroundColor(.gray)
        }
    }
}

// MARK: - Previews

#Preview("Debug Tray - Collapsed") {
    VStack {
        Spacer()
        DebugTray(debugData: DebugData(
            pipelineSteps: [
                DebugPipelineStep(
                    rawText: "CAYMUS CABERNET SAUVIGNON NAPA VALLEY",
                    normalizedText: "caymus cabernet sauvignon",
                    bottleIndex: 0,
                    fuzzyMatch: FuzzyMatchDebug(
                        candidate: "Caymus Cabernet Sauvignon",
                        scores: FuzzyMatchScores(
                            ratio: 0.85,
                            partialRatio: 0.95,
                            tokenSortRatio: 0.90,
                            phoneticBonus: 0.05,
                            weightedScore: 0.91
                        ),
                        rating: 4.5
                    ),
                    llmValidation: nil,
                    finalResult: DebugFinalResult(
                        wineName: "Caymus Cabernet Sauvignon",
                        confidence: 0.91,
                        source: "database"
                    ),
                    stepFailed: nil,
                    includedInResults: true
                ),
                DebugPipelineStep(
                    rawText: "UNKNOWN WINE TEXT",
                    normalizedText: "unknown wine text",
                    bottleIndex: 1,
                    fuzzyMatch: FuzzyMatchDebug(
                        candidate: "One Wine",
                        scores: FuzzyMatchScores(
                            ratio: 0.3,
                            partialRatio: 0.5,
                            tokenSortRatio: 0.4,
                            phoneticBonus: 0.0,
                            weightedScore: 0.42
                        ),
                        rating: 3.5
                    ),
                    llmValidation: LLMValidationDebug(
                        isValidMatch: false,
                        wineName: nil,
                        confidence: 0.3,
                        reasoning: "Text does not match any known wine"
                    ),
                    finalResult: nil,
                    stepFailed: "llm_validation",
                    includedInResults: false
                )
            ],
            totalOcrTexts: 5,
            bottlesDetected: 4,
            textsMatched: 3,
            llmCallsMade: 1
        ))
    }
    .background(Color.black)
}
