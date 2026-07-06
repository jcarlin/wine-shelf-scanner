import Foundation

/// Stage of the staged waiting experience shown while a scan is processing.
enum ScanProgressStage: Equatable {
    case findingBottles
    case readingLabels
    case rankingPicks

    var localizedText: String {
        switch self {
        case .findingBottles:
            return NSLocalizedString("processing.findingBottles", comment: "Scan stage: finding bottles")
        case .readingLabels:
            return NSLocalizedString("processing.readingLabels", comment: "Scan stage: reading labels")
        case .rankingPicks:
            return NSLocalizedString("processing.rankingPicks", comment: "Scan stage: ranking picks")
        }
    }
}

/// Pure elapsed-time → stage mapping for the scan waiting UI.
///
/// Stages mirror what the Detect+Read backend actually does: bottle
/// detection (~0–5s), per-crop label reads (~5–14s), ranking/enrichment
/// (14s+). After 25s a reassurance line is shown.
enum ScanProgressModel {
    static let readingLabelsStart: TimeInterval = 5
    static let rankingPicksStart: TimeInterval = 14
    static let reassuranceStart: TimeInterval = 25

    static func stage(forElapsed elapsed: TimeInterval) -> ScanProgressStage {
        switch elapsed {
        case ..<readingLabelsStart:
            return .findingBottles
        case ..<rankingPicksStart:
            return .readingLabels
        default:
            return .rankingPicks
        }
    }

    static func showsReassurance(forElapsed elapsed: TimeInterval) -> Bool {
        elapsed >= reassuranceStart
    }
}
