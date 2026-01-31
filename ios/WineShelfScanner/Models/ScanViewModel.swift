import SwiftUI

/// ViewModel for managing scan state and service calls
@MainActor
class ScanViewModel: ObservableObject {
    @Published private(set) var state: ScanState = .idle

    private let scanService: ScanServiceProtocol

    init(scanService: ScanServiceProtocol? = nil) {
        // Use provided service, or create real API client using Config
        if let scanService = scanService {
            self.scanService = scanService
        } else {
            // Use centralized Config for API URL
            self.scanService = ScanAPIClient(baseURL: Config.apiBaseURL)
        }
    }

    /// Perform scan with given image
    func performScan(with image: UIImage) {
        state = .processing

        Task {
            do {
                let response = try await scanService.scan(image: image)
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
}
