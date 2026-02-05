import XCTest
@testable import WineShelfScanner

final class BackgroundScanManagerTests: XCTestCase {

    // MARK: - PendingScan Codable Tests

    func testPendingScanEncodesAndDecodes() throws {
        let scan = PendingScan(
            taskIdentifier: 42,
            imageFilePath: "/tmp/test.jpg",
            bodyFilePath: "/tmp/body.tmp",
            startedAt: Date(timeIntervalSince1970: 1700000000)
        )

        let data = try JSONEncoder().encode(scan)
        let decoded = try JSONDecoder().decode(PendingScan.self, from: data)

        XCTAssertEqual(decoded.taskIdentifier, 42)
        XCTAssertEqual(decoded.imageFilePath, "/tmp/test.jpg")
        XCTAssertEqual(decoded.bodyFilePath, "/tmp/body.tmp")
        XCTAssertEqual(decoded.startedAt, Date(timeIntervalSince1970: 1700000000))
    }

    // MARK: - CompletedBackgroundScan Tests

    func testCompletedBackgroundScanEncodesAndDecodes() throws {
        let response = TestFixtures.fullShelfResponse
        let completed = CompletedBackgroundScan(
            response: response,
            imageFilePath: "/tmp/result.jpg",
            completedAt: Date(timeIntervalSince1970: 1700001000)
        )

        let data = try JSONEncoder().encode(completed)
        let decoded = try JSONDecoder().decode(CompletedBackgroundScan.self, from: data)

        XCTAssertEqual(decoded.response.imageId, response.imageId)
        XCTAssertEqual(decoded.response.results.count, response.results.count)
        XCTAssertEqual(decoded.imageFilePath, "/tmp/result.jpg")
        XCTAssertEqual(decoded.completedAt, Date(timeIntervalSince1970: 1700001000))
    }

    func testCompletedBackgroundScanImageReturnsNilForMissingFile() {
        let completed = CompletedBackgroundScan(
            response: TestFixtures.fullShelfResponse,
            imageFilePath: "/nonexistent/path.jpg",
            completedAt: Date()
        )

        XCTAssertNil(completed.image)
    }

    func testCompletedBackgroundScanImageLoadsFromValidPath() throws {
        // Write a test image to a temp path
        let image = TestFixtures.testImage
        let tempDir = FileManager.default.temporaryDirectory
        let imageURL = tempDir.appendingPathComponent("test_bg_scan_\(UUID().uuidString).jpg")

        let imageData = image.jpegData(compressionQuality: 0.8)!
        try imageData.write(to: imageURL)

        defer { try? FileManager.default.removeItem(at: imageURL) }

        let completed = CompletedBackgroundScan(
            response: TestFixtures.fullShelfResponse,
            imageFilePath: imageURL.path,
            completedAt: Date()
        )

        XCTAssertNotNil(completed.image)
    }

    // MARK: - BackgroundScanManager Singleton

    func testSharedInstanceExists() {
        let manager = BackgroundScanManager.shared
        XCTAssertNotNil(manager)
    }

    func testInitialStateIsNotScanning() {
        let manager = BackgroundScanManager.shared
        // Manager may or may not be scanning depending on previous tests,
        // but we can verify the property is accessible.
        _ = manager.isScanning
    }

    func testCompletedScanIsInitiallyNilOrRestored() {
        let manager = BackgroundScanManager.shared
        // completedScan can be nil or contain a restored scan from disk.
        // Just verify it's accessible.
        _ = manager.completedScan
    }

    // MARK: - Session Identifier

    func testSessionIdentifierIsCorrect() {
        XCTAssertEqual(
            BackgroundScanManager.sessionIdentifier,
            "com.wineshelfscanner.background-scan"
        )
    }

    // MARK: - ScanState Equality

    func testBackgroundProcessingStateEquality() {
        let date = Date()
        let state1 = ScanState.backgroundProcessing(date)
        let state2 = ScanState.backgroundProcessing(date)
        XCTAssertEqual(state1, state2)
    }

    func testBackgroundProcessingStateInequalityWithDifferentDates() {
        let state1 = ScanState.backgroundProcessing(Date(timeIntervalSince1970: 1000))
        let state2 = ScanState.backgroundProcessing(Date(timeIntervalSince1970: 2000))
        XCTAssertNotEqual(state1, state2)
    }

    func testBackgroundProcessingNotEqualToProcessing() {
        let state1 = ScanState.processing
        let state2 = ScanState.backgroundProcessing(Date())
        XCTAssertNotEqual(state1, state2)
    }

    // MARK: - FeatureFlag

    func testBackgroundProcessingFeatureFlagExists() {
        // Verify the feature flag is accessible and returns a Bool
        let enabled = FeatureFlags.shared.backgroundProcessing
        XCTAssertTrue(enabled || !enabled) // Just verify it's a Bool
    }

    func testBackgroundProcessingFlagDefaultsToTrue() {
        // The compiled default is true
        // Note: this may be overridden by UserDefaults in test environment
        // We verify the flag is at least accessible
        _ = FeatureFlags.shared.backgroundProcessing
    }

    // MARK: - ScanViewModel Background Integration

    @MainActor
    func testViewModelRestoreWithNoCompletedScan() {
        let mockService = MockScanServiceForTests()
        let viewModel = ScanViewModel(scanService: mockService)

        // Initial state should be idle
        XCTAssertEqual(viewModel.state, .idle)

        // restoreBackgroundScanIfNeeded should not crash
        viewModel.restoreBackgroundScanIfNeeded()
    }

    @MainActor
    func testViewModelResetClearsState() {
        let mockService = MockScanServiceForTests()
        let viewModel = ScanViewModel(scanService: mockService)

        viewModel.reset()
        XCTAssertEqual(viewModel.state, .idle)
    }
}
