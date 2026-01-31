import Foundation

/// App configuration
enum Config {
    /// API base URL (from xcconfig → Info.plist, or env var, or fallback)
    static var apiBaseURL: URL {
        // 1. Check for runtime environment override (useful for testing)
        if let urlString = ProcessInfo.processInfo.environment["API_BASE_URL"],
           let url = URL(string: urlString) {
            return url
        }

        // 2. Read from Info.plist (set via xcconfig)
        if let urlString = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String,
           !urlString.isEmpty,
           let url = URL(string: urlString) {
            return url
        }

        // 3. Fallback to production URL
        return URL(string: "https://wine-scanner-api-82762985464.us-central1.run.app")!
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
