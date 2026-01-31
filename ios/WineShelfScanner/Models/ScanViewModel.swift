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

    init(scanService: ScanServiceProtocol? = nil) {
        // Use provided service, or create real API client using Config
        if let scanService = scanService {
            self.scanService = scanService
        } else {
            // Use centralized Config for API URL
            self.scanService = ScanAPIClient(baseURL: Config.apiBaseURL)
        }

        // Debug mode always enabled
        self.debugMode = true
    }

    /// Perform scan with given image
    func performScan(with image: UIImage) {
        state = .processing

        Task {
            do {
                let response = try await scanService.scan(image: image, debug: debugMode)
                state = .results(response, image)
            } catch {
                state = .error(error.localizedDescription)
            }
        }
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
