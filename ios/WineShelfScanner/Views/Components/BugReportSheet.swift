import SwiftUI

/// Modal sheet for submitting a bug report
struct BugReportSheet: View {
    let reportType: BugReportType
    let errorMessage: String?
    let imageId: String?
    let metadata: BugReportMetadata?

    @Environment(\.dismiss) private var dismiss
    @State private var userDescription: String = ""
    @State private var isSubmitting = false
    @State private var submitted = false

    private let reportService = BugReportService()

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                if submitted {
                    submittedView
                } else {
                    reportFormView
                }
            }
            .padding()
            .navigationTitle(NSLocalizedString("bugReport.reportIssue", comment: "Report sheet title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(NSLocalizedString("bugReport.cancel", comment: "Cancel button")) { dismiss() }
                        .accessibilityIdentifier("bugReportCancelButton")
                }
            }
        }
        .accessibilityIdentifier("bugReportSheet")
    }

    private var reportFormView: some View {
        VStack(spacing: 16) {
            // Context summary
            VStack(alignment: .leading, spacing: 8) {
                Label(contextLabel, systemImage: contextIcon)
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(10)

            // User description
            VStack(alignment: .leading, spacing: 6) {
                Text(NSLocalizedString("bugReport.whatHappened", comment: "What happened label"))
                    .font(.subheadline)
                    .foregroundColor(.secondary)

                TextField(NSLocalizedString("bugReport.describePlaceholder", comment: "Describe placeholder"), text: $userDescription, axis: .vertical)
                    .lineLimit(3...5)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("bugReportTextField")
            }

            Spacer()

            // Submit button
            Button {
                submitReport()
            } label: {
                if isSubmitting {
                    ProgressView()
                        .tint(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                } else {
                    Text(NSLocalizedString("bugReport.submitReport", comment: "Submit button"))
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                }
            }
            .background(Color.accentColor)
            .cornerRadius(12)
            .disabled(isSubmitting)
            .accessibilityIdentifier("bugReportSubmitButton")
        }
    }

    private var submittedView: some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 48))
                .foregroundColor(.green)

            Text(NSLocalizedString("bugReport.submitted", comment: "Report submitted"))
                .font(.headline)

            Text(NSLocalizedString("bugReport.thanksImprove", comment: "Thanks message"))
                .font(.subheadline)
                .foregroundColor(.secondary)

            Spacer()

            Button(NSLocalizedString("bugReport.done", comment: "Done button")) { dismiss() }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("bugReportDoneButton")
        }
        .accessibilityIdentifier("bugReportConfirmation")
        .padding(.top, 32)
    }

    private var contextLabel: String {
        switch reportType {
        case .error:
            return NSLocalizedString("bugReport.scanError", comment: "Scan error context")
        case .partialDetection:
            return NSLocalizedString("bugReport.someNotRecognized", comment: "Partial detection context")
        case .fullFailure:
            return NSLocalizedString("bugReport.noBottlesIdentified", comment: "Full failure context")
        case .wrongWine:
            return NSLocalizedString("bugReport.wrongMatch", comment: "Wrong wine context")
        }
    }

    private var contextIcon: String {
        switch reportType {
        case .error:
            return "exclamationmark.triangle"
        case .partialDetection:
            return "eye.trianglebadge.exclamationmark"
        case .fullFailure:
            return "xmark.circle"
        case .wrongWine:
            return "arrow.triangle.2.circlepath"
        }
    }

    private func submitReport() {
        isSubmitting = true

        // Determine error type string from error message
        let errorType: String? = {
            guard reportType == .error, let msg = errorMessage else { return nil }
            let lower = msg.lowercased()
            if lower.contains("network") || lower.contains("connect") {
                return "NETWORK_ERROR"
            } else if lower.contains("server") {
                return "SERVER_ERROR"
            } else if lower.contains("timeout") || lower.contains("timed out") {
                return "TIMEOUT"
            } else if lower.contains("decode") || lower.contains("parse") {
                return "PARSE_ERROR"
            }
            return nil
        }()

        Task {
            do {
                try await reportService.submitReport(
                    reportType: reportType,
                    errorType: errorType,
                    errorMessage: errorMessage,
                    userDescription: userDescription.isEmpty ? nil : String(userDescription.prefix(500)),
                    imageId: imageId,
                    metadata: metadata
                )
                await MainActor.run {
                    submitted = true
                    isSubmitting = false
                }
            } catch {
                #if DEBUG
                print("Bug report submission failed: \(error)")
                #endif
                // Fire and forget — still show success to avoid frustrating the user
                await MainActor.run {
                    submitted = true
                    isSubmitting = false
                }
            }
        }
    }
}
