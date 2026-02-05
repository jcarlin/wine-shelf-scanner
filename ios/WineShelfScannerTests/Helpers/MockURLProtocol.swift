import Foundation

/// URLProtocol subclass for mocking network requests in unit tests
///
/// Usage:
/// ```swift
/// let config = URLSessionConfiguration.ephemeral
/// config.protocolClasses = [MockURLProtocol.self]
/// let session = URLSession(configuration: config)
///
/// MockURLProtocol.requestHandler = { request in
///     let response = HTTPURLResponse(
///         url: request.url!,
///         statusCode: 200,
///         httpVersion: nil,
///         headerFields: nil
///     )!
///     let data = TestFixtures.validJSONResponse.data(using: .utf8)!
///     return (response, data)
/// }
/// ```
class MockURLProtocol: URLProtocol {

    /// Handler for processing requests. Set this in your test setUp.
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    /// Captured requests for inspection in tests
    static var capturedRequests: [URLRequest] = []

    /// Reset the mock state between tests
    static func reset() {
        requestHandler = nil
        capturedRequests = []
    }

    override class func canInit(with request: URLRequest) -> Bool {
        // Handle all requests
        return true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        return request
    }

    override func startLoading() {
        // Capture the request for inspection
        MockURLProtocol.capturedRequests.append(request)

        guard let handler = MockURLProtocol.requestHandler else {
            let error = NSError(
                domain: "MockURLProtocol",
                code: -1,
                userInfo: [NSLocalizedDescriptionKey: "No request handler set"]
            )
            client?.urlProtocol(self, didFailWithError: error)
            return
        }

        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {
        // Nothing to do here
    }
}

// MARK: - Test Helpers

extension MockURLProtocol {

    /// Create a mock session configured with this protocol
    static func mockSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return URLSession(configuration: config)
    }

    /// Set up a successful JSON response
    static func setSuccessResponse(json: String, statusCode: Int = 200) {
        requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: statusCode,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            let data = json.data(using: .utf8)!
            return (response, data)
        }
    }

    /// Set up an error response
    static func setErrorResponse(statusCode: Int) {
        requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: statusCode,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }
    }

    /// Set up a network error
    static func setNetworkError(_ error: Error) {
        requestHandler = { _ in
            throw error
        }
    }

    /// Get the last captured request
    static var lastRequest: URLRequest? {
        capturedRequests.last
    }

    /// Check if a specific header was set on the last request
    static func headerValue(for key: String) -> String? {
        lastRequest?.value(forHTTPHeaderField: key)
    }

    /// Get the body data from the last request
    static var lastRequestBody: Data? {
        lastRequest?.httpBody
    }
}

// MARK: - Common Response Builders

extension MockURLProtocol {

    /// Set up a successful scan response
    static func setSuccessfulScanResponse() {
        setSuccessResponse(json: TestFixtures.validJSONResponse)
    }

    /// Set up an empty results scan response
    static func setEmptyScanResponse() {
        setSuccessResponse(json: TestFixtures.minimalJSONResponse)
    }

    /// Set up a malformed JSON response
    static func setMalformedJSONResponse() {
        setSuccessResponse(json: TestFixtures.malformedJSON)
    }

    /// Set up a server error response
    static func setServerError(code: Int = 500) {
        setErrorResponse(statusCode: code)
    }

    /// Set up a successful feedback response
    static func setSuccessfulFeedbackResponse() {
        setSuccessResponse(json: """
        {"success": true, "message": "Feedback recorded"}
        """)
    }

    /// Set up a rejected feedback response
    static func setRejectedFeedbackResponse() {
        setSuccessResponse(json: """
        {"success": false, "message": "Feedback rejected"}
        """)
    }

    /// Set up a successful bug report response
    static func setSuccessfulReportResponse() {
        setSuccessResponse(json: """
        {"success": true, "report_id": "test-report-id-123"}
        """)
    }

    /// Set up a rejected bug report response
    static func setRejectedReportResponse() {
        setSuccessResponse(json: """
        {"success": false, "report_id": ""}
        """)
    }
}
