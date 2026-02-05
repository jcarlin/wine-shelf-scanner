import SwiftUI

/// ViewModel for managing scan state and service calls
@MainActor
class ScanViewModel: ObservableObject {
    @Published private(set) var state: ScanState = .idle
    @Published var debugMode: Bool = true {
        didSet {
            // Persist debug mode preference
            UserDefaults.standard.set(debugMode, forKey: "debugModeEnabled")
        }
    }

    private let scanService: ScanServiceProtocol
    private let networkMonitor: NetworkMonitor

    init(scanService: ScanServiceProtocol? = nil, networkMonitor: NetworkMonitor? = nil) {
        // Use provided service, or create real API client using Config
        if let scanService = scanService {
            self.scanService = scanService
        } else {
            // Use centralized Config for API URL
            self.scanService = ScanAPIClient(baseURL: Config.apiBaseURL)
        }

        self.networkMonitor = networkMonitor ?? NetworkMonitor.shared

        // Debug mode always enabled
        self.debugMode = true
    }

    /// Perform scan with given image, adapting compression to network conditions
    func performScan(with image: UIImage) {
        state = .processing

        let quality = FeatureFlags.shared.offlineCache
            ? networkMonitor.compressionQuality
            : 0.8

        Task {
            do {
                let response = try await scanService.scan(
                    image: image,
                    debug: debugMode,
                    compressionQuality: quality
                )
                // Cache result for offline access
                ScanCacheService.shared.save(response: response, image: image)
                state = .results(response, image)
            } catch {
                // On network failure, fall back to cache if offline and cache is available
                if FeatureFlags.shared.offlineCache,
                   !networkMonitor.isConnected,
                   let cached = ScanCacheService.shared.loadAll().first {
                    state = .cachedResults(cached.response, cached.image, cached.timestamp)
                } else {
                    state = .error(error.localizedDescription)
                }
            }
        }
    }

    /// Whether there are cached scans available for offline viewing
    var hasCachedScans: Bool {
        FeatureFlags.shared.offlineCache && ScanCacheService.shared.hasCachedScans
    }

    /// Load cached scans for offline viewing
    func loadCachedScans() -> [(response: ScanResponse, image: UIImage?, timestamp: Date)] {
        ScanCacheService.shared.loadAll()
    }

    /// Show the most recent cached scan
    func showCachedScans() {
        guard let cached = ScanCacheService.shared.loadAll().first else { return }
        state = .cachedResults(cached.response, cached.image, cached.timestamp)
    }

    /// Show a specific cached scan by entry
    func showCachedScan(_ entry: ScanCacheService.CachedScan) {
        let image = ScanCacheService.shared.loadImage(for: entry)
        state = .cachedResults(entry.response, image, entry.timestamp)
    }

    /// Reset to idle state
    func reset() {
        state = .idle
    }

    /// Toggle debug mode
    func toggleDebugMode() {
        debugMode.toggle()
    }
}
