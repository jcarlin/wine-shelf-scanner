import XCTest
@testable import WineShelfScanner

@MainActor
final class ScanViewModelTests: XCTestCase {

    var viewModel: ScanViewModel!
    var mockScanService: MockScanServiceForTests!

    override func setUp() async throws {
        try await super.setUp()
        mockScanService = MockScanServiceForTests()
        viewModel = ScanViewModel(scanService: mockScanService)
    }

    override func tearDown() async throws {
        viewModel = nil
        mockScanService = nil
        try await super.tearDown()
    }

    // MARK: - Initial State Tests

    func testInitialStateIsIdle() {
        XCTAssertEqual(viewModel.state, .idle)
    }

    func testDebugModeDefaultsToTrue() {
        XCTAssertTrue(viewModel.debugMode)
    }

    // MARK: - State Transitions

    func testPerformScanTransitionsToProcessing() {
        let image = TestFixtures.testImage

        viewModel.performScan(with: image)

        // State should immediately be processing
        XCTAssertEqual(viewModel.state, .processing)
    }

    func testSuccessfulScanTransitionsToResults() async throws {
        let image = TestFixtures.testImage
        mockScanService.responseToReturn = TestFixtures.fullShelfResponse

        viewModel.performScan(with: image)

        // Wait for async task to complete
        try await Task.sleep(nanoseconds: 100_000_000) // 0.1 second

        if case .results(let response, _) = viewModel.state {
            XCTAssertEqual(response.imageId, TestFixtures.fullShelfResponse.imageId)
            XCTAssertEqual(response.results.count, TestFixtures.fullShelfResponse.results.count)
        } else {
            XCTFail("Expected results state, got \(viewModel.state)")
        }
    }

    func testFailedScanTransitionsToError() async throws {
        let image = TestFixtures.testImage
        mockScanService.errorToThrow = ScanError.networkError(NSError(domain: "test", code: -1))

        viewModel.performScan(with: image)

        // Wait for async task to complete
        try await Task.sleep(nanoseconds: 100_000_000) // 0.1 second

        if case .error(let message) = viewModel.state {
            XCTAssertFalse(message.isEmpty)
        } else {
            XCTFail("Expected error state, got \(viewModel.state)")
        }
    }

    func testResetTransitionsToIdle() async throws {
        let image = TestFixtures.testImage
        mockScanService.responseToReturn = TestFixtures.fullShelfResponse

        viewModel.performScan(with: image)

        // Wait for results
        try await Task.sleep(nanoseconds: 100_000_000)

        // Now reset
        viewModel.reset()

        XCTAssertEqual(viewModel.state, .idle)
    }

    // MARK: - Async Behavior

    func testPerformScanCallsScanServiceWithImage() async throws {
        let image = TestFixtures.testImage

        viewModel.performScan(with: image)

        // Wait for async task to complete
        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(mockScanService.scanCallCount, 1)
        XCTAssertNotNil(mockScanService.lastImage)
    }

    func testPerformScanPassesDebugFlag() async throws {
        let image = TestFixtures.testImage
        viewModel.debugMode = true

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(mockScanService.lastDebugFlag, true)
    }

    func testPerformScanPassesDebugFlagWhenDisabled() async throws {
        let image = TestFixtures.testImage
        viewModel.debugMode = false

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(mockScanService.lastDebugFlag, false)
    }

    // MARK: - Error Handling

    func testNetworkErrorShowsLocalizedMessage() async throws {
        let image = TestFixtures.testImage
        let networkError = NSError(domain: NSURLErrorDomain, code: NSURLErrorNotConnectedToInternet)
        mockScanService.errorToThrow = ScanError.networkError(networkError)

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        if case .error(let message) = viewModel.state {
            XCTAssertTrue(message.contains("Network"))
        } else {
            XCTFail("Expected error state")
        }
    }

    func testTimeoutErrorShowsMessage() async throws {
        let image = TestFixtures.testImage
        mockScanService.errorToThrow = ScanError.timeout

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        if case .error(let message) = viewModel.state {
            XCTAssertTrue(message.contains("timed out"))
        } else {
            XCTFail("Expected error state")
        }
    }

    func testInvalidImageErrorShowsMessage() async throws {
        let image = TestFixtures.testImage
        mockScanService.errorToThrow = ScanError.invalidImage

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        if case .error(let message) = viewModel.state {
            XCTAssertTrue(message.contains("image"))
        } else {
            XCTFail("Expected error state")
        }
    }

    func testServerErrorShowsMessage() async throws {
        let image = TestFixtures.testImage
        mockScanService.errorToThrow = ScanError.serverError(500)

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        if case .error(let message) = viewModel.state {
            XCTAssertTrue(message.contains("500") || message.contains("Server"))
        } else {
            XCTFail("Expected error state")
        }
    }

    func testDecodingErrorShowsMessage() async throws {
        let image = TestFixtures.testImage
        let decodingError = DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "test"))
        mockScanService.errorToThrow = ScanError.decodingError(decodingError)

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        if case .error(let message) = viewModel.state {
            XCTAssertFalse(message.isEmpty)
        } else {
            XCTFail("Expected error state")
        }
    }

    // MARK: - Debug Mode

    func testToggleDebugModeFlipsValue() {
        let initialValue = viewModel.debugMode

        viewModel.toggleDebugMode()

        XCTAssertNotEqual(viewModel.debugMode, initialValue)

        viewModel.toggleDebugMode()

        XCTAssertEqual(viewModel.debugMode, initialValue)
    }

    // MARK: - Dependency Injection

    func testUsesInjectedScanService() async throws {
        let customMock = MockScanServiceForTests()
        customMock.responseToReturn = TestFixtures.partialDetectionResponse

        let customViewModel = ScanViewModel(scanService: customMock)
        let image = TestFixtures.testImage

        customViewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(customMock.scanCallCount, 1)

        if case .results(let response, _) = customViewModel.state {
            XCTAssertEqual(response.imageId, "test-partial")
        } else {
            XCTFail("Expected results state")
        }
    }

    // MARK: - Multiple Scans

    func testMultipleScansIncrementCallCount() async throws {
        let image = TestFixtures.testImage

        viewModel.performScan(with: image)
        try await Task.sleep(nanoseconds: 100_000_000)

        viewModel.reset()
        viewModel.performScan(with: image)
        try await Task.sleep(nanoseconds: 100_000_000)

        XCTAssertEqual(mockScanService.scanCallCount, 2)
    }

    // MARK: - State Preservation

    func testResultsStatePreservesImage() async throws {
        let image = TestFixtures.testImage
        mockScanService.responseToReturn = TestFixtures.fullShelfResponse

        viewModel.performScan(with: image)

        try await Task.sleep(nanoseconds: 100_000_000)

        if case .results(_, let capturedImage) = viewModel.state {
            XCTAssertNotNil(capturedImage)
        } else {
            XCTFail("Expected results state with image")
        }
    }
}
