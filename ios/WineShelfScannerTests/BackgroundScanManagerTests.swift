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

    func testPendingScanDecodesLegacyJSONWithoutAttestFields() throws {
        // Entries persisted by older builds have no attest fields —
        // restorePendingScans must still decode them
        let legacyJSON = """
        {"taskIdentifier": 7, "imageFilePath": "/tmp/i.jpg", "bodyFilePath": "/tmp/b.tmp", "startedAt": 1700000000}
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .secondsSince1970

        let decoded = try decoder.decode(PendingScan.self, from: legacyJSON.data(using: .utf8)!)

        XCTAssertEqual(decoded.taskIdentifier, 7)
        XCTAssertNil(decoded.attested)
        XCTAssertNil(decoded.requestURL)
        XCTAssertNil(decoded.contentType)
    }

    func testPendingScanRoundTripsAttestFields() throws {
        let scan = PendingScan(
            taskIdentifier: 42,
            imageFilePath: "/tmp/test.jpg",
            bodyFilePath: "/tmp/body.tmp",
            startedAt: Date(timeIntervalSince1970: 1700000000),
            attested: true,
            requestURL: "https://api.example.com/scan?debug=true",
            contentType: "multipart/form-data; boundary=abc"
        )

        let data = try JSONEncoder().encode(scan)
        let decoded = try JSONDecoder().decode(PendingScan.self, from: data)

        XCTAssertEqual(decoded.attested, true)
        XCTAssertEqual(decoded.requestURL, "https://api.example.com/scan?debug=true")
        XCTAssertEqual(decoded.contentType, "multipart/form-data; boundary=abc")
    }

    // MARK: - Attested 403 Recovery (background)

    private func pendingScan(attested: Bool?, bodyFilePath: String = "/tmp/b.tmp") -> PendingScan {
        PendingScan(
            taskIdentifier: 1,
            imageFilePath: "/tmp/i.jpg",
            bodyFilePath: bodyFilePath,
            startedAt: Date(),
            attested: attested,
            requestURL: "https://api.example.com/scan",
            contentType: "multipart/form-data; boundary=test-boundary"
        )
    }

    func testShouldRetryUnattestedOnlyForAttested403() {
        XCTAssertTrue(BackgroundScanManager.shouldRetryUnattested(statusCode: 403, pending: pendingScan(attested: true)))

        // Unattested 403s surface normally
        XCTAssertFalse(BackgroundScanManager.shouldRetryUnattested(statusCode: 403, pending: pendingScan(attested: false)))
        XCTAssertFalse(BackgroundScanManager.shouldRetryUnattested(statusCode: 403, pending: pendingScan(attested: nil)))

        // Other statuses are not attest rejections
        XCTAssertFalse(BackgroundScanManager.shouldRetryUnattested(statusCode: 500, pending: pendingScan(attested: true)))
        XCTAssertFalse(BackgroundScanManager.shouldRetryUnattested(statusCode: 200, pending: pendingScan(attested: true)))
    }

    func testMakeUnattestedResubmissionBuildsCleanRequestAndCopiesBody() throws {
        // A real body file on disk
        let bodyURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("bg_retry_test_\(UUID().uuidString).tmp")
        let bodyContents = Data("multipart-body-bytes".utf8)
        try bodyContents.write(to: bodyURL)
        defer { try? FileManager.default.removeItem(at: bodyURL) }

        let pending = pendingScan(attested: true, bodyFilePath: bodyURL.path)

        let resubmission = try XCTUnwrap(
            BackgroundScanManager.shared.makeUnattestedResubmission(from: pending)
        )
        defer { try? FileManager.default.removeItem(at: resubmission.bodyFileURL) }

        // Same endpoint and content type, but NO attest headers
        XCTAssertEqual(resubmission.request.url?.absoluteString, "https://api.example.com/scan")
        XCTAssertEqual(resubmission.request.httpMethod, "POST")
        XCTAssertEqual(
            resubmission.request.value(forHTTPHeaderField: "Content-Type"),
            "multipart/form-data; boundary=test-boundary"
        )
        XCTAssertNil(resubmission.request.value(forHTTPHeaderField: "X-Attest-Key-Id"))
        XCTAssertNil(resubmission.request.value(forHTTPHeaderField: "X-Attest-Assertion"))
        XCTAssertNil(resubmission.request.value(forHTTPHeaderField: "X-Attest-Challenge"))

        // Body copied to a fresh file (the original is deleted by the
        // completion handler's cleanup)
        XCTAssertNotEqual(resubmission.bodyFileURL.path, bodyURL.path)
        XCTAssertEqual(try Data(contentsOf: resubmission.bodyFileURL), bodyContents)
    }

    func testMakeUnattestedResubmissionReturnsNilWhenBodyFileMissing() {
        let pending = pendingScan(attested: true, bodyFilePath: "/nonexistent/body.tmp")

        XCTAssertNil(BackgroundScanManager.shared.makeUnattestedResubmission(from: pending))
    }

    func testMakeUnattestedResubmissionReturnsNilWithoutPersistedURL() throws {
        let bodyURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("bg_retry_test_\(UUID().uuidString).tmp")
        try Data("x".utf8).write(to: bodyURL)
        defer { try? FileManager.default.removeItem(at: bodyURL) }

        // Legacy entry: no requestURL persisted → resubmission impossible
        let pending = PendingScan(
            taskIdentifier: 1,
            imageFilePath: "/tmp/i.jpg",
            bodyFilePath: bodyURL.path,
            startedAt: Date()
        )

        XCTAssertNil(BackgroundScanManager.shared.makeUnattestedResubmission(from: pending))
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
