import Foundation

/// Warms the backend when the app becomes active.
///
/// The production Cloud Run instance can take tens of seconds to wake from
/// a fresh deploy — pinging /health while the user picks a photo hides the
/// cold start. Fire-and-forget: failures are ignored.
final class WarmupService {
    static let shared = WarmupService()

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL = Config.apiBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    /// Fire-and-forget warmup ping.
    func warmUp() {
        Task { await self.ping() }
    }

    /// GET {base}/health. Returns whether the backend answered 2xx.
    @discardableResult
    func ping() async -> Bool {
        var request = URLRequest(url: baseURL.appendingPathComponent("health"))
        request.timeoutInterval = 30
        do {
            let (_, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { return false }
            return (200...299).contains(http.statusCode)
        } catch {
            return false
        }
    }
}
