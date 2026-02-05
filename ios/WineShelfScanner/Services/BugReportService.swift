import Foundation

/// Service for submitting bug reports to the backend
class BugReportService {
    private let baseURL: URL
    private let session: URLSession

    /// Anonymous device identifier (shared with FeedbackService)
    static var deviceId: String {
        let key = "wine_scanner_device_id"
        if let existingId = UserDefaults.standard.string(forKey: key) {
            return existingId
        }
        let newId = UUID().uuidString
        UserDefaults.standard.set(newId, forKey: key)
        return newId
    }

    /// App version from bundle
    private static var appVersion: String? {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
    }

    init(baseURL: URL = Config.apiBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    /// Submit a bug report
    /// - Parameters:
    ///   - reportType: Type of report (error, partial_detection, full_failure)
    ///   - errorType: Error category if applicable
    ///   - errorMessage: Error message shown to user
    ///   - userDescription: Optional free-text from user
    ///   - imageId: Image ID from scan response if available
    ///   - metadata: Optional metadata (detection counts, confidence scores)
    func submitReport(
        reportType: BugReportType,
        errorType: String? = nil,
        errorMessage: String? = nil,
        userDescription: String? = nil,
        imageId: String? = nil,
        metadata: BugReportMetadata? = nil
    ) async throws {
        let url = baseURL.appendingPathComponent("report")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10.0

        let report = BugReport(
            reportType: reportType.rawValue,
            errorType: errorType,
            errorMessage: errorMessage,
            userDescription: userDescription,
            imageId: imageId,
            deviceId: Self.deviceId,
            platform: "ios",
            appVersion: Self.appVersion,
            timestamp: ISO8601DateFormatter().string(from: Date()),
            metadata: metadata
        )

        request.httpBody = try JSONEncoder().encode(report)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw BugReportError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw BugReportError.serverError(httpResponse.statusCode)
        }

        if let decoded = try? JSONDecoder().decode(BugReportResponse.self, from: data),
           !decoded.success {
            throw BugReportError.reportRejected
        }

        #if DEBUG
        print("Bug report submitted: \(reportType.rawValue)")
        #endif
    }
}

/// Errors from bug report submission
enum BugReportError: LocalizedError {
    case invalidResponse
    case serverError(Int)
    case reportRejected
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid server response"
        case .serverError(let code):
            return "Server error: \(code)"
        case .reportRejected:
            return "Report was not accepted"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}
