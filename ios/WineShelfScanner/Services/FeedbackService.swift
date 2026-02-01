import Foundation

/// Service for submitting user feedback on wine matches
class FeedbackService {
    private let baseURL: URL
    private let session: URLSession

    /// Anonymous device identifier (persisted across sessions)
    private static var deviceId: String {
        let key = "wine_scanner_device_id"
        if let existingId = UserDefaults.standard.string(forKey: key) {
            return existingId
        }
        let newId = UUID().uuidString
        UserDefaults.standard.set(newId, forKey: key)
        return newId
    }

    init(baseURL: URL = Config.apiBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    /// Submit feedback for a wine match
    /// - Parameters:
    ///   - imageId: ID from the scan response
    ///   - wineName: Wine name shown to user
    ///   - isCorrect: True for thumbs up, false for thumbs down
    ///   - correctedName: User-provided correct name (optional, for incorrect matches)
    ///   - ocrText: Original OCR text if available (for debugging)
    func submitFeedback(
        imageId: String,
        wineName: String,
        isCorrect: Bool,
        correctedName: String? = nil,
        ocrText: String? = nil
    ) async throws {
        let url = baseURL.appendingPathComponent("feedback")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10.0

        let payload: [String: Any?] = [
            "image_id": imageId,
            "wine_name": wineName,
            "is_correct": isCorrect,
            "corrected_name": correctedName,
            "ocr_text": ocrText,
            "device_id": Self.deviceId
        ]

        // Filter out nil values
        let filteredPayload = payload.compactMapValues { $0 }
        request.httpBody = try JSONSerialization.data(withJSONObject: filteredPayload)

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw FeedbackError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw FeedbackError.serverError(httpResponse.statusCode)
        }

        // Verify success in response
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let success = json["success"] as? Bool,
           !success {
            throw FeedbackError.feedbackRejected
        }

        #if DEBUG
        print("Feedback submitted: \(isCorrect ? "correct" : "incorrect") for \(wineName)")
        #endif
    }
}

/// Errors from feedback submission
enum FeedbackError: LocalizedError {
    case invalidResponse
    case serverError(Int)
    case feedbackRejected
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid server response"
        case .serverError(let code):
            return "Server error: \(code)"
        case .feedbackRejected:
            return "Feedback was not accepted"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        }
    }
}
