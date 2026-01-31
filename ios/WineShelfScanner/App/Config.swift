import Foundation

/// App configuration
enum Config {
    /// API base URL
    static var apiBaseURL: URL {
        // Check for environment override first
        if let urlString = ProcessInfo.processInfo.environment["API_BASE_URL"],
           let url = URL(string: urlString) {
            return url
        }

        #if DEBUG
        // Local development - use Mac's IP for simulator access
        return URL(string: "http://192.168.1.112:8000")!
        #else
        // Production - Cloud Run URL
        // Update this after deploying to Cloud Run
        return URL(string: "https://wine-scanner-api-XXXXX.run.app")!
        #endif
    }

    /// Whether to use mock data (for UI development)
    static var useMocks: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.environment["USE_MOCKS"] == "true"
        #else
        return false
        #endif
    }

    /// Request timeout in seconds
    static let requestTimeout: TimeInterval = 15.0
}
