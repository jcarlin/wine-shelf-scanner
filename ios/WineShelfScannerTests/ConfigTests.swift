import XCTest
@testable import WineShelfScanner

final class ConfigTests: XCTestCase {

    // Store original environment values
    var originalApiBaseUrl: String?
    var originalUseMocks: String?

    override func setUp() {
        super.setUp()
        // Save original environment values
        originalApiBaseUrl = ProcessInfo.processInfo.environment["API_BASE_URL"]
        originalUseMocks = ProcessInfo.processInfo.environment["USE_MOCKS"]
    }

    override func tearDown() {
        // Note: We cannot restore environment variables in Swift
        // Tests that modify environment are inherently order-dependent
        super.tearDown()
    }

    // MARK: - API Base URL Tests

    func testFallbackURLIsValid() {
        // When no environment variable or Info.plist value is set,
        // Config should return a valid production URL
        let fallbackURL = URL(string: "https://wine-scanner-api-82762985464.us-central1.run.app")!

        // The actual URL should be a valid URL
        XCTAssertNotNil(Config.apiBaseURL)
        XCTAssertTrue(Config.apiBaseURL.absoluteString.hasPrefix("https://"))
    }

    func testApiBaseURLIsValidURL() {
        let url = Config.apiBaseURL
        XCTAssertNotNil(url.scheme)
        XCTAssertTrue(url.scheme == "http" || url.scheme == "https")
        XCTAssertNotNil(url.host)
    }

    func testApiBaseURLDoesNotHaveTrailingSlash() {
        // A clean base URL shouldn't have a trailing slash
        // (paths like "/scan" will be appended)
        let url = Config.apiBaseURL
        XCTAssertFalse(url.absoluteString.hasSuffix("/"))
    }

    // MARK: - Request Timeout Tests

    func testRequestTimeoutIsPositive() {
        XCTAssertGreaterThan(Config.requestTimeout, 0)
    }

    func testRequestTimeoutIsReasonable() {
        // Timeout should be reasonable (between 10 and 120 seconds)
        XCTAssertGreaterThanOrEqual(Config.requestTimeout, 10)
        XCTAssertLessThanOrEqual(Config.requestTimeout, 120)
    }

    func testRequestTimeoutIs45Seconds() {
        // Per Config.swift comment: Vision API can take 10-20s, so 45s is allowed
        XCTAssertEqual(Config.requestTimeout, 45.0)
    }

    // MARK: - Use Mocks Tests

    func testUseMocksDefaultsToFalseInProduction() {
        // In release builds, useMocks should always be false
        // In debug builds, it depends on the environment variable
        #if DEBUG
        // In debug, behavior depends on env var
        // If USE_MOCKS is not set, should be false
        if ProcessInfo.processInfo.environment["USE_MOCKS"] == nil {
            XCTAssertFalse(Config.useMocks)
        }
        #else
        XCTAssertFalse(Config.useMocks)
        #endif
    }

    // MARK: - URL Path Construction Tests

    func testScanPathCanBeAppended() {
        let baseURL = Config.apiBaseURL
        let scanURL = baseURL.appendingPathComponent("scan")

        XCTAssertTrue(scanURL.absoluteString.contains("/scan"))
        XCTAssertNotEqual(baseURL, scanURL)
    }

    func testFeedbackPathCanBeAppended() {
        let baseURL = Config.apiBaseURL
        let feedbackURL = baseURL.appendingPathComponent("feedback")

        XCTAssertTrue(feedbackURL.absoluteString.contains("/feedback"))
        XCTAssertNotEqual(baseURL, feedbackURL)
    }

    // MARK: - Configuration Consistency Tests

    func testConfigValuesAreConsistent() {
        // Multiple accesses should return the same values
        let url1 = Config.apiBaseURL
        let url2 = Config.apiBaseURL

        XCTAssertEqual(url1, url2)

        let timeout1 = Config.requestTimeout
        let timeout2 = Config.requestTimeout

        XCTAssertEqual(timeout1, timeout2)
    }

    // MARK: - Type Safety Tests

    func testApiBaseURLIsNotOptional() {
        // This test verifies the type is URL, not URL?
        // The test passes if it compiles, since we can use the URL directly
        let url: URL = Config.apiBaseURL
        XCTAssertNotNil(url)
    }

    func testRequestTimeoutIsTimeInterval() {
        let timeout: TimeInterval = Config.requestTimeout
        XCTAssertNotNil(timeout)
    }

    func testUseMocksIsBool() {
        let useMocks: Bool = Config.useMocks
        // Just verify we got a value (true or false)
        XCTAssertTrue(useMocks == true || useMocks == false)
    }
}
