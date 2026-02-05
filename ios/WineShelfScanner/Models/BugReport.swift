import Foundation

/// A bug report submitted by the user
struct BugReport: Codable {
    let reportType: String
    let errorType: String?
    let errorMessage: String?
    let userDescription: String?
    let imageId: String?
    let deviceId: String
    let platform: String
    let appVersion: String?
    let timestamp: String?
    let metadata: BugReportMetadata?

    enum CodingKeys: String, CodingKey {
        case reportType = "report_type"
        case errorType = "error_type"
        case errorMessage = "error_message"
        case userDescription = "user_description"
        case imageId = "image_id"
        case deviceId = "device_id"
        case platform
        case appVersion = "app_version"
        case timestamp
        case metadata
    }
}

/// Optional metadata attached to a bug report
struct BugReportMetadata: Codable {
    let winesDetected: Int?
    let winesInFallback: Int?
    let confidenceScores: [Double]?

    enum CodingKeys: String, CodingKey {
        case winesDetected = "wines_detected"
        case winesInFallback = "wines_in_fallback"
        case confidenceScores = "confidence_scores"
    }
}

/// Response from the /report endpoint
struct BugReportResponse: Codable {
    let success: Bool
    let reportId: String

    enum CodingKeys: String, CodingKey {
        case success
        case reportId = "report_id"
    }
}

/// Report types matching backend expectations
enum BugReportType: String {
    case error = "error"
    case partialDetection = "partial_detection"
    case fullFailure = "full_failure"
    case wrongWine = "wrong_wine"
}
