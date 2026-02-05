import SwiftUI
import Combine

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
    private let backgroundManager: BackgroundScanManager
    private var cancellables = Set<AnyCancellable>()

    init(scanService: ScanServiceProtocol? = nil, backgroundManager: BackgroundScanManager? = nil) {
        // Use provided service, or create real API client using Config
        if let scanService = scanService {
            self.scanService = scanService
        } else {
            // Use centralized Config for API URL
            self.scanService = ScanAPIClient(baseURL: Config.apiBaseURL)
        }

        self.backgroundManager = backgroundManager ?? BackgroundScanManager.shared

        // Debug mode always enabled
        self.debugMode = true

        // Observe background scan completion
        observeBackgroundScanCompletion()
    }

    /// Perform scan with given image.
    ///
    /// When the `backgroundProcessing` feature flag is enabled, uses a background
    /// URLSession so the upload continues even if the user leaves the app.
    /// Otherwise falls back to the foreground async/await path.
    func performScan(with image: UIImage) {
        if FeatureFlags.shared.backgroundProcessing {
            performBackgroundScan(with: image)
        } else {
            performForegroundScan(with: image)
        }
    }

    /// Whether there are cached scans available for offline viewing
    var hasCachedScans: Bool {
        ScanCacheService.shared.hasCachedScans
    }

    /// Load cached scans for offline viewing
    func loadCachedScans() -> [(response: ScanResponse, image: UIImage?, timestamp: Date)] {
        ScanCacheService.shared.loadAll()
    }

    /// Reset to idle state
    func reset() {
        state = .idle
        backgroundManager.clearCompletedScan()
    }

    /// Toggle debug mode
    func toggleDebugMode() {
        debugMode.toggle()
    }

    /// Restore a completed background scan on app launch.
    /// Called from WineShelfScannerApp when the app starts.
    func restoreBackgroundScanIfNeeded() {
        if let completed = backgroundManager.completedScan,
           let image = completed.image {
            state = .results(completed.response, image)
        } else if backgroundManager.isScanning {
            state = .backgroundProcessing(Date())
        }
    }

    // MARK: - Private

    private func performForegroundScan(with image: UIImage) {
        state = .processing

        Task {
            do {
                let response = try await scanService.scan(image: image, debug: debugMode)
                // Cache result for offline access
                ScanCacheService.shared.save(response: response, image: image)
                state = .results(response, image)
            } catch {
                state = .error(error.localizedDescription)
            }
        }
    }

    private func performBackgroundScan(with image: UIImage) {
        state = .processing

        do {
            try backgroundManager.startScan(image: image, debug: debugMode)
        } catch {
            state = .error(error.localizedDescription)
        }
    }

    private func observeBackgroundScanCompletion() {
        backgroundManager.$completedScan
            .receive(on: DispatchQueue.main)
            .sink { [weak self] completed in
                guard let self = self else { return }
                guard let completed = completed else {
                    // A nil after we were scanning means failure
                    if case .processing = self.state {
                        self.state = .error("Scan failed. Please try again.")
                    } else if case .backgroundProcessing = self.state {
                        self.state = .error("Scan failed. Please try again.")
                    }
                    return
                }

                if let image = completed.image {
                    self.state = .results(completed.response, image)
                } else {
                    self.state = .error("Scan completed but the image could not be loaded.")
                }
            }
            .store(in: &cancellables)

        backgroundManager.$isScanning
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isScanning in
                guard let self = self else { return }
                // If background scanning started and we're in foreground processing,
                // keep showing the processing spinner (same UX).
                if isScanning, case .processing = self.state {
                    // Stay in .processing — no UX change while user is in the app
                }
            }
            .store(in: &cancellables)
    }
}
