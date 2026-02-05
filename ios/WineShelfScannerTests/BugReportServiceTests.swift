import XCTest
@testable import WineShelfScanner

final class BugReportServiceTests: XCTestCase {

    var reportService: BugReportService!
    var mockSession: URLSession!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        mockSession = MockURLProtocol.mockSession()
        reportService = BugReportService(
            baseURL: URL(string: "https://test-api.example.com")!,
            session: mockSession
        )
    }

    override func tearDown() {
        reportService = nil
        mockSession = nil
        MockURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - Request Construction

    func testRequestUsesPostMethod() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .error,
            errorMessage: "Network error"
        )

        XCTAssertEqual(MockURLProtocol.lastRequest?.httpMethod, "POST")
    }

    func testRequestUsesJSONContentType() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .error,
            errorMessage: "Network error"
        )

        let contentType = MockURLProtocol.headerValue(for: "Content-Type")
        XCTAssertEqual(contentType, "application/json")
    }

    func testRequestURLAppendsReportPath() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .error,
            errorMessage: "Test error"
        )

        let url = MockURLProtocol.lastRequest?.url
        XCTAssertTrue(url?.path.contains("/report") ?? false)
    }

    func testRequestIncludesRequiredFields() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .error,
            errorType: "NETWORK_ERROR",
            errorMessage: "Connection failed"
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertEqual(json["report_type"] as? String, "error")
        XCTAssertEqual(json["error_type"] as? String, "NETWORK_ERROR")
        XCTAssertEqual(json["error_message"] as? String, "Connection failed")
        XCTAssertEqual(json["platform"] as? String, "ios")
        XCTAssertNotNil(json["device_id"])
        XCTAssertNotNil(json["timestamp"])
    }

    func testRequestIncludesOptionalFields() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .partialDetection,
            userDescription: "Only 2 out of 5 bottles found",
            imageId: "img-abc-123",
            metadata: BugReportMetadata(
                winesDetected: 2,
                winesInFallback: 3,
                confidenceScores: [0.85, 0.72]
            )
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertEqual(json["report_type"] as? String, "partial_detection")
        XCTAssertEqual(json["user_description"] as? String, "Only 2 out of 5 bottles found")
        XCTAssertEqual(json["image_id"] as? String, "img-abc-123")

        if let metadata = json["metadata"] as? [String: Any] {
            XCTAssertEqual(metadata["wines_detected"] as? Int, 2)
            XCTAssertEqual(metadata["wines_in_fallback"] as? Int, 3)
        } else {
            XCTFail("Expected metadata in request body")
        }
    }

    func testFullFailureReportType() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .fullFailure,
            metadata: BugReportMetadata(
                winesDetected: 0,
                winesInFallback: 5,
                confidenceScores: nil
            )
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertEqual(json["report_type"] as? String, "full_failure")
    }

    // MARK: - Error Handling

    func testServerErrorThrowsWithCode() async {
        MockURLProtocol.setServerError(code: 500)

        do {
            try await reportService.submitReport(
                reportType: .error,
                errorMessage: "Test"
            )
            XCTFail("Expected server error")
        } catch let error as BugReportError {
            if case .serverError(let code) = error {
                XCTAssertEqual(code, 500)
            } else {
                XCTFail("Expected serverError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testReportRejectedThrowsError() async {
        MockURLProtocol.setRejectedReportResponse()

        do {
            try await reportService.submitReport(
                reportType: .error,
                errorMessage: "Test"
            )
            XCTFail("Expected report rejected error")
        } catch let error as BugReportError {
            if case .reportRejected = error {
                // Expected
            } else {
                XCTFail("Expected reportRejected, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - Device ID

    func testDeviceIdIsIncludedInReport() async throws {
        MockURLProtocol.setSuccessfulReportResponse()

        try await reportService.submitReport(
            reportType: .error,
            errorMessage: "Test"
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
              let deviceId = json["device_id"] as? String else {
            XCTFail("Could not parse device_id from request body")
            return
        }

        XCTAssertFalse(deviceId.isEmpty)
    }
}
