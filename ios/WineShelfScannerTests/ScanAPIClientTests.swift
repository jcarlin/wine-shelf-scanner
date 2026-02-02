import XCTest
@testable import WineShelfScanner

final class ScanAPIClientTests: XCTestCase {

    var apiClient: ScanAPIClient!
    var mockSession: URLSession!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        mockSession = MockURLProtocol.mockSession()
        apiClient = ScanAPIClient(
            baseURL: URL(string: "https://test-api.example.com")!,
            session: mockSession
        )
    }

    override func tearDown() {
        apiClient = nil
        mockSession = nil
        MockURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - Request Construction

    func testRequestUsesPostMethod() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        XCTAssertEqual(MockURLProtocol.lastRequest?.httpMethod, "POST")
    }

    func testRequestUsesMultipartFormData() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        let contentType = MockURLProtocol.headerValue(for: "Content-Type")
        XCTAssertTrue(contentType?.contains("multipart/form-data") ?? false)
        XCTAssertTrue(contentType?.contains("boundary=") ?? false)
    }

    func testRequestIncludesImageAsJPEG() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        let body = MockURLProtocol.lastRequestBody
        XCTAssertNotNil(body)

        // Check for JPEG content type in multipart body
        if let bodyString = body.flatMap({ String(data: $0, encoding: .utf8) }) {
            XCTAssertTrue(bodyString.contains("Content-Type: image/jpeg"))
            XCTAssertTrue(bodyString.contains("filename=\"shelf.jpg\""))
        } else {
            // Body contains binary data, check for multipart structure
            XCTAssertGreaterThan(body?.count ?? 0, 0)
        }
    }

    func testRequestIncludesDebugQueryParamWhenTrue() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        _ = try await apiClient.scan(image: TestFixtures.testImage, debug: true)

        let url = MockURLProtocol.lastRequest?.url
        XCTAssertTrue(url?.absoluteString.contains("debug=true") ?? false)
    }

    func testRequestExcludesDebugQueryParamWhenFalse() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        let url = MockURLProtocol.lastRequest?.url
        XCTAssertFalse(url?.absoluteString.contains("debug=") ?? true)
    }

    func testRequestURLAppendsScanPath() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        let url = MockURLProtocol.lastRequest?.url
        XCTAssertTrue(url?.path.contains("/scan") ?? false)
    }

    // MARK: - Response Handling

    func testSuccessfulResponseDecodesCorrectly() async throws {
        MockURLProtocol.setSuccessfulScanResponse()

        let response = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        XCTAssertEqual(response.imageId, "test-json")
        XCTAssertEqual(response.results.count, 1)
        XCTAssertEqual(response.results[0].wineName, "Opus One")
        XCTAssertEqual(response.results[0].rating, 4.8)
        XCTAssertEqual(response.results[0].confidence, 0.91)
    }

    func testEmptyResultsArrayDecodesCorrectly() async throws {
        MockURLProtocol.setEmptyScanResponse()

        let response = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        XCTAssertEqual(response.imageId, "test")
        XCTAssertEqual(response.results.count, 0)
        XCTAssertEqual(response.fallbackList.count, 0)
    }

    func testNullRatingsDecodeAsNil() async throws {
        MockURLProtocol.setSuccessResponse(json: TestFixtures.jsonWithNullRatings)

        let response = try await apiClient.scan(image: TestFixtures.testImage, debug: false)

        XCTAssertNil(response.results[0].rating)
        XCTAssertNil(response.fallbackList[0].rating)
    }

    // MARK: - Error Cases

    func testInvalidImageThrowsError() async {
        // Create an image that will fail JPEG conversion
        // Using a 0x0 image
        let emptyImage = UIImage()

        do {
            _ = try await apiClient.scan(image: emptyImage, debug: false)
            XCTFail("Expected invalidImage error")
        } catch let error as ScanError {
            if case .invalidImage = error {
                // Expected
            } else {
                XCTFail("Expected invalidImage, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testServerErrorThrowsWithStatusCode() async {
        MockURLProtocol.setServerError(code: 500)

        do {
            _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)
            XCTFail("Expected server error")
        } catch let error as ScanError {
            if case .serverError(let code) = error {
                XCTAssertEqual(code, 500)
            } else {
                XCTFail("Expected serverError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testNon200ResponseThrowsServerError() async {
        MockURLProtocol.setErrorResponse(statusCode: 404)

        do {
            _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)
            XCTFail("Expected server error")
        } catch let error as ScanError {
            if case .serverError(let code) = error {
                XCTAssertEqual(code, 404)
            } else {
                XCTFail("Expected serverError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testMalformedJSONThrowsDecodingError() async {
        MockURLProtocol.setMalformedJSONResponse()

        do {
            _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)
            XCTFail("Expected decoding error")
        } catch let error as ScanError {
            if case .decodingError = error {
                // Expected
            } else {
                XCTFail("Expected decodingError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    func testNetworkErrorThrowsScanError() async {
        let networkError = NSError(domain: NSURLErrorDomain, code: NSURLErrorNotConnectedToInternet)
        MockURLProtocol.setNetworkError(networkError)

        do {
            _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)
            XCTFail("Expected network error")
        } catch let error as ScanError {
            if case .networkError = error {
                // Expected
            } else {
                XCTFail("Expected networkError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - Edge Cases

    func test299ResponseIsSuccess() async throws {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 299,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = TestFixtures.validJSONResponse.data(using: .utf8)!
            return (response, data)
        }

        let response = try await apiClient.scan(image: TestFixtures.testImage, debug: false)
        XCTAssertNotNil(response)
    }

    func test300ResponseIsError() async {
        MockURLProtocol.setErrorResponse(statusCode: 300)

        do {
            _ = try await apiClient.scan(image: TestFixtures.testImage, debug: false)
            XCTFail("Expected server error")
        } catch let error as ScanError {
            if case .serverError(let code) = error {
                XCTAssertEqual(code, 300)
            } else {
                XCTFail("Expected serverError, got \(error)")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - Response with Debug Data

    func testResponseWithDebugDataDecodesCorrectly() async throws {
        let jsonWithDebug = """
        {
            "image_id": "test-debug",
            "results": [
                {
                    "wine_name": "Caymus",
                    "rating": 4.5,
                    "confidence": 0.91,
                    "bbox": {"x": 0.15, "y": 0.12, "width": 0.09, "height": 0.38}
                }
            ],
            "fallback_list": [],
            "debug": {
                "pipeline_steps": [
                    {
                        "raw_text": "CAYMUS",
                        "normalized_text": "caymus",
                        "bottle_index": 0,
                        "fuzzy_match": {
                            "candidate": "Caymus",
                            "scores": {
                                "ratio": 1.0,
                                "partial_ratio": 1.0,
                                "token_sort_ratio": 1.0,
                                "phonetic_bonus": 0.0,
                                "weighted_score": 1.0
                            },
                            "rating": 4.5
                        },
                        "llm_validation": null,
                        "final_result": {
                            "wine_name": "Caymus",
                            "confidence": 0.91,
                            "source": "database"
                        },
                        "step_failed": null,
                        "included_in_results": true
                    }
                ],
                "total_ocr_texts": 1,
                "bottles_detected": 1,
                "texts_matched": 1,
                "llm_calls_made": 0
            }
        }
        """
        MockURLProtocol.setSuccessResponse(json: jsonWithDebug)

        let response = try await apiClient.scan(image: TestFixtures.testImage, debug: true)

        XCTAssertNotNil(response.debug)
        XCTAssertEqual(response.debug?.pipelineSteps.count, 1)
        XCTAssertEqual(response.debug?.totalOcrTexts, 1)
        XCTAssertEqual(response.debug?.textsMatched, 1)
        XCTAssertEqual(response.debug?.llmCallsMade, 0)
    }
}
