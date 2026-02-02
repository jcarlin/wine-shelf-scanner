import Foundation

/// Centralized accessibility identifiers for UI testing
/// These must match the identifiers set in the SwiftUI views
enum AccessibilityIdentifiers {

    // MARK: - Idle State
    enum Idle {
        static let scanShelfButton = "scanShelfButton"
        static let choosePhotoButton = "choosePhotoButton"
    }

    // MARK: - Processing State
    enum Processing {
        static let spinner = "processingSpinner"
    }

    // MARK: - Results State
    enum Results {
        static let view = "resultsView"
        static let newScanButton = "newScanButton"
        static let overlayContainer = "overlayContainer"
        static let partialDetectionToast = "partialDetectionToast"

        // Fallback list
        static let fallbackContainer = "fallbackContainer"
        static let fallbackListHeader = "fallbackListHeader"
        static let fallbackList = "fallbackList"

        /// Generate rating badge identifier for a wine
        /// - Parameter wineName: The wine name (will be sanitized)
        /// - Returns: Accessibility identifier for the badge
        static func ratingBadge(wineName: String) -> String {
            let sanitized = wineName.lowercased()
                .replacingOccurrences(of: " ", with: "-")
                .replacingOccurrences(of: "'", with: "")
            return "ratingBadge_\(sanitized)"
        }
    }

    // MARK: - Detail Sheet
    enum DetailSheet {
        static let view = "wineDetailSheet"
        static let wineName = "detailSheetWineName"
        static let rating = "detailSheetRating"
        static let confidenceLabel = "detailSheetConfidenceLabel"

        // Feedback controls
        static let thumbsUpButton = "thumbsUpButton"
        static let thumbsDownButton = "thumbsDownButton"
        static let correctionTextField = "correctionTextField"
        static let feedbackConfirmation = "feedbackConfirmation"
        static let feedbackPrompt = "feedbackPrompt"
    }

    // MARK: - Debug Tray
    enum DebugTray {
        static let view = "debugTray"
        static let header = "debugTrayHeader"
        static let expandButton = "debugTrayExpand"
        static let statSummary = "debugStatSummary"
        static let stepsList = "debugStepsList"

        /// Generate step row identifier
        static func stepRow(_ index: Int) -> String {
            "debugStep_\(index)"
        }
    }

    // MARK: - Error State
    enum Error {
        static let view = "errorView"
        static let message = "errorMessage"
        static let retryButton = "retryButton"
        static let startOverButton = "startOverButton"
    }
}
