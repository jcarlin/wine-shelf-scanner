import XCTest
@testable import WineShelfScanner

final class FeedbackServiceTests: XCTestCase {

    var feedbackService: FeedbackService!
    var mockSession: URLSession!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        mockSession = MockURLProtocol.mockSession()
        feedbackService = FeedbackService(
            baseURL: URL(string: "https://test-api.example.com")!,
            session: mockSession
        )
    }

    override func tearDown() {
        feedbackService = nil
        mockSession = nil
        MockURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - Device ID Tests

    func testDeviceIdIsPersistedAcrossSessions() {
        // Clear any existing device ID
        let key = "wine_scanner_device_id"
        UserDefaults.standard.removeObject(forKey: key)

        // First access - should generate new ID
        let firstService = FeedbackService()
        MockURLProtocol.setSuccessfulFeedbackResponse()

        // Capture the device ID from the request
        Task {
            try? await firstService.submitFeedback(
                imageId: "test",
                wineName: "Test Wine",
                isCorrect: true
            )
        }

        // Wait a moment for the async task
        let expectation = XCTestExpectation(description: "Wait for first request")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            expectation.fulfill()
        }
        wait(for: [expectation], timeout: 1.0)

        // Get the persisted device ID
        let persistedId = UserDefaults.standard.string(forKey: key)
        XCTAssertNotNil(persistedId)

        // Second access - should use same ID
        let secondService = FeedbackService()
        MockURLProtocol.capturedRequests.removeAll()

        Task {
            try? await secondService.submitFeedback(
                imageId: "test2",
                wineName: "Test Wine 2",
                isCorrect: true
            )
        }

        let expectation2 = XCTestExpectation(description: "Wait for second request")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            expectation2.fulfill()
        }
        wait(for: [expectation2], timeout: 1.0)

        // Verify ID is still the same
        let persistedId2 = UserDefaults.standard.string(forKey: key)
        XCTAssertEqual(persistedId, persistedId2)
    }

    func testDeviceIdIsUUIDFormat() {
        let key = "wine_scanner_device_id"
        // Clear any existing
        UserDefaults.standard.removeObject(forKey: key)

        // Trigger device ID generation
        _ = FeedbackService()

        // Try to submit to trigger ID generation
        MockURLProtocol.setSuccessfulFeedbackResponse()

        let expectation = XCTestExpectation(description: "Wait for request")

        Task {
            try? await feedbackService.submitFeedback(
                imageId: "test",
                wineName: "Test",
                isCorrect: true
            )
            expectation.fulfill()
        }

        wait(for: [expectation], timeout: 2.0)

        // Check if the last request body contains a UUID-formatted device_id
        if let body = MockURLProtocol.lastRequestBody,
           let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any],
           let deviceId = json["device_id"] as? String {
            // UUID format: 8-4-4-4-12 hexadecimal characters
            let uuidPattern = "^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$"
            let regex = try? NSRegularExpression(pattern: uuidPattern, options: .caseInsensitive)
            let range = NSRange(deviceId.startIndex..., in: deviceId)
            let matches = regex?.numberOfMatches(in: deviceId, range: range) ?? 0
            XCTAssertEqual(matches, 1, "Device ID should be in UUID format")
        }
    }

    // MARK: - Request Construction

    func testRequestUsesPostMethod() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true
        )

        XCTAssertEqual(MockURLProtocol.lastRequest?.httpMethod, "POST")
    }

    func testRequestUsesJSONContentType() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true
        )

        let contentType = MockURLProtocol.headerValue(for: "Content-Type")
        XCTAssertEqual(contentType, "application/json")
    }

    func testRequestIncludesAllRequiredFields() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertEqual(json["image_id"] as? String, "test-123")
        XCTAssertEqual(json["wine_name"] as? String, "Opus One")
        XCTAssertEqual(json["is_correct"] as? Bool, true)
        XCTAssertNotNil(json["device_id"])
    }

    func testRequestIncludesCorrectedNameWhenProvided() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Wrong Wine",
            isCorrect: false,
            correctedName: "Correct Wine Name"
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertEqual(json["corrected_name"] as? String, "Correct Wine Name")
        XCTAssertEqual(json["is_correct"] as? Bool, false)
    }

    func testRequestIncludesOcrTextWhenProvided() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true,
            ocrText: "OPUS ONE NAPA VALLEY 2019"
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertEqual(json["ocr_text"] as? String, "OPUS ONE NAPA VALLEY 2019")
    }

    // MARK: - Nil Field Handling

    func testRequestOmitsNilCorrectedName() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true,
            correctedName: nil
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertNil(json["corrected_name"])
    }

    func testRequestOmitsNilOcrText() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true,
            ocrText: nil
        )

        guard let body = MockURLProtocol.lastRequestBody,
              let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any] else {
            XCTFail("Could not parse request body")
            return
        }

        XCTAssertNil(json["ocr_text"])
    }

    // MARK: - Error Handling

    func testServerErrorThrowsWithCode() async {
        MockURLProtocol.setServerError(code: 500)

        do {
            try await feedbackService.submitFeedback(
                imageId: "test-123",
                wineName: "Opus One",
                isCorrect: true
            )
            XCTFail("Expected server error")
        } catch let error as FeedbackError {
            if case .serverError(let code) = error {
                XCTAssertEqual(code, 500)
            } else {
                XCTFail("Expected serverError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testFeedbackRejectedThrowsError() async {
        MockURLProtocol.setRejectedFeedbackResponse()

        do {
            try await feedbackService.submitFeedback(
                imageId: "test-123",
                wineName: "Opus One",
                isCorrect: true
            )
            XCTFail("Expected feedback rejected error")
        } catch let error as FeedbackError {
            if case .feedbackRejected = error {
                // Expected
            } else {
                XCTFail("Expected feedbackRejected, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func test404ErrorThrowsServerError() async {
        MockURLProtocol.setErrorResponse(statusCode: 404)

        do {
            try await feedbackService.submitFeedback(
                imageId: "test-123",
                wineName: "Opus One",
                isCorrect: true
            )
            XCTFail("Expected server error")
        } catch let error as FeedbackError {
            if case .serverError(let code) = error {
                XCTAssertEqual(code, 404)
            } else {
                XCTFail("Expected serverError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - URL Construction

    func testRequestURLAppendsFeedbackPath() async throws {
        MockURLProtocol.setSuccessfulFeedbackResponse()

        try await feedbackService.submitFeedback(
            imageId: "test-123",
            wineName: "Opus One",
            isCorrect: true
        )

        let url = MockURLProtocol.lastRequest?.url
        XCTAssertTrue(url?.path.contains("/feedback") ?? false)
    }
}
