import Foundation

/// Fetches server-driven client configuration (GET /config) on launch and
/// applies it as FeatureFlags overrides.
///
/// On failure the existing value is kept: UserDefaults overrides persist
/// across launches, and the compiled default (false) remains the ultimate
/// fallback — so the paywall can be activated (or killed) server-side
/// without an app update.
final class RemoteFlagsService {
    static let shared = RemoteFlagsService()

    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL = Config.apiBaseURL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    private struct ClientConfig: Decodable {
        let featureSubscription: Bool

        enum CodingKeys: String, CodingKey {
            case featureSubscription = "feature_subscription"
        }
    }

    /// Fire-and-forget refresh for app launch.
    func refreshOnLaunch() {
        Task { await self.refresh() }
    }

    /// GET /config and apply flag overrides. Returns whether config was applied.
    @discardableResult
    func refresh() async -> Bool {
        var request = URLRequest(url: baseURL.appendingPathComponent("config"))
        request.timeoutInterval = 15
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200...299).contains(http.statusCode) else {
                return false
            }
            let config = try JSONDecoder().decode(ClientConfig.self, from: data)
            FeatureFlags.shared.setOverride("feature_subscription", value: config.featureSubscription)
            return true
        } catch {
            return false
        }
    }
}
