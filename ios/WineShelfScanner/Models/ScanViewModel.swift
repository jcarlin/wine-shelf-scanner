import SwiftUI

/// ViewModel for managing scan state and service calls
@MainActor
class ScanViewModel: ObservableObject {
    @Published private(set) var state: ScanState = .idle

    private let scanService: ScanServiceProtocol

    init(scanService: ScanServiceProtocol? = nil) {
        // Use real API client if base URL is configured, otherwise use mock
        if let scanService = scanService {
            self.scanService = scanService
        } else if let baseURL = Self.apiBaseURL {
            self.scanService = ScanAPIClient(baseURL: baseURL)
        } else {
            self.scanService = MockScanService()
        }
    }

    /// API base URL from environment or defaults
    private static var apiBaseURL: URL? {
        // Check for environment override
        if let urlString = ProcessInfo.processInfo.environment["API_BASE_URL"],
           let url = URL(string: urlString) {
            return url
        }

        // Default to localhost for development
        #if DEBUG
        return URL(string: "http://localhost:8000")
        #else
        // Production URL - update when deployed
        return URL(string: "https://wine-scanner-api.run.app")
        #endif
    }

    /// Start a new scan (legacy - opens camera via ContentView)
    func startScan() {
        // This is now handled by ContentView's camera sheet
        // Keeping for backward compatibility with tests
        guard let testImage = loadTestImage() else {
            state = .error("Could not load test image")
            return
        }
        performScan(with: testImage)
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

    // MARK: - Private

    private func loadTestImage() -> UIImage? {
        // Try to load from bundle first
        if let bundleImage = UIImage(named: "test_shelf") {
            return bundleImage
        }

        // Fallback: create a placeholder image for development
        return createPlaceholderImage()
    }

    private func createPlaceholderImage() -> UIImage {
        let size = CGSize(width: 400, height: 300)
        let renderer = UIGraphicsImageRenderer(size: size)

        return renderer.image { context in
            // Background
            UIColor.darkGray.setFill()
            context.fill(CGRect(origin: .zero, size: size))

            // Text
            let text = "Test Shelf Image"
            let attrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 24),
                .foregroundColor: UIColor.white
            ]
            let textSize = text.size(withAttributes: attrs)
            let textRect = CGRect(
                x: (size.width - textSize.width) / 2,
                y: (size.height - textSize.height) / 2,
                width: textSize.width,
                height: textSize.height
            )
            text.draw(in: textRect, withAttributes: attrs)
        }
    }
}
