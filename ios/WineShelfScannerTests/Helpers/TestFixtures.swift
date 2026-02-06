import UIKit
@testable import WineShelfScanner

/// Shared test data for Wine Shelf Scanner unit tests
enum TestFixtures {

    // MARK: - Mock Scan Responses

    /// Full shelf response with multiple wines
    static let fullShelfResponse = ScanResponse(
        imageId: "test-full-shelf",
        results: [
            WineResult(
                wineName: "Opus One",
                rating: 4.8,
                confidence: 0.91,
                bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)
            ),
            WineResult(
                wineName: "Caymus Cabernet Sauvignon",
                rating: 4.5,
                confidence: 0.88,
                bbox: BoundingBox(x: 0.25, y: 0.15, width: 0.08, height: 0.35)
            ),
            WineResult(
                wineName: "Jordan Cabernet Sauvignon",
                rating: 4.3,
                confidence: 0.82,
                bbox: BoundingBox(x: 0.35, y: 0.10, width: 0.09, height: 0.40)
            ),
            WineResult(
                wineName: "La Crema Pinot Noir",
                rating: 3.9,
                confidence: 0.75,
                bbox: BoundingBox(x: 0.55, y: 0.18, width: 0.08, height: 0.32)
            )
        ],
        fallbackList: [],
        debug: nil
    )

    /// Partial detection with some wines in fallback
    static let partialDetectionResponse = ScanResponse(
        imageId: "test-partial",
        results: [
            WineResult(
                wineName: "Opus One",
                rating: 4.8,
                confidence: 0.91,
                bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)
            )
        ],
        fallbackList: [
            FallbackWine(wineName: "Caymus Cabernet Sauvignon", rating: 4.5),
            FallbackWine(wineName: "Unknown Wine", rating: nil)
        ],
        debug: nil
    )

    /// Full failure - only fallback results
    static let fullFailureResponse = ScanResponse(
        imageId: "test-failure",
        results: [],
        fallbackList: [
            FallbackWine(wineName: "Opus One", rating: 4.8),
            FallbackWine(wineName: "Caymus Cabernet Sauvignon", rating: 4.5)
        ],
        debug: nil
    )

    /// Empty results (no wines detected)
    static let emptyResultsResponse = ScanResponse(
        imageId: "test-empty",
        results: [],
        fallbackList: [],
        debug: nil
    )

    /// Response with null ratings
    static let nullRatingsResponse = ScanResponse(
        imageId: "test-null-ratings",
        results: [
            WineResult(
                wineName: "Unknown Wine",
                rating: nil,
                confidence: 0.75,
                bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)
            )
        ],
        fallbackList: [
            FallbackWine(wineName: "Another Unknown", rating: nil)
        ],
        debug: nil
    )

    /// Response with debug data
    static let responseWithDebug = ScanResponse(
        imageId: "test-debug",
        results: [
            WineResult(
                wineName: "Caymus Cabernet Sauvignon",
                rating: 4.5,
                confidence: 0.91,
                bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)
            )
        ],
        fallbackList: [],
        debug: DebugData(
            pipelineSteps: [
                DebugPipelineStep(
                    rawText: "CAYMUS CABERNET SAUVIGNON NAPA VALLEY",
                    normalizedText: "caymus cabernet sauvignon",
                    bottleIndex: 0,
                    fuzzyMatch: FuzzyMatchDebug(
                        candidate: "Caymus Cabernet Sauvignon",
                        scores: FuzzyMatchScores(
                            ratio: 0.85,
                            partialRatio: 0.95,
                            tokenSortRatio: 0.90,
                            phoneticBonus: 0.05,
                            weightedScore: 0.91
                        ),
                        rating: 4.5
                    ),
                    llmValidation: nil,
                    finalResult: DebugFinalResult(
                        wineName: "Caymus Cabernet Sauvignon",
                        confidence: 0.91,
                        source: "database"
                    ),
                    stepFailed: nil,
                    includedInResults: true
                )
            ],
            totalOcrTexts: 5,
            bottlesDetected: 4,
            textsMatched: 3,
            llmCallsMade: 0
        )
    )

    // MARK: - JSON Fixtures

    /// Valid JSON response for full shelf
    static let validJSONResponse = """
    {
        "image_id": "test-json",
        "results": [
            {
                "wine_name": "Opus One",
                "rating": 4.8,
                "confidence": 0.91,
                "bbox": {"x": 0.15, "y": 0.12, "width": 0.09, "height": 0.38}
            }
        ],
        "fallback_list": []
    }
    """

    /// Minimal valid JSON response
    static let minimalJSONResponse = """
    {"image_id":"test","results":[],"fallback_list":[]}
    """

    /// Malformed JSON
    static let malformedJSON = "{ invalid json }"

    /// JSON with null ratings
    static let jsonWithNullRatings = """
    {
        "image_id": "test-null",
        "results": [
            {
                "wine_name": "Unknown Wine",
                "rating": null,
                "confidence": 0.75,
                "bbox": {"x": 0.1, "y": 0.2, "width": 0.08, "height": 0.3}
            }
        ],
        "fallback_list": [
            {"wine_name": "Another Unknown", "rating": null}
        ]
    }
    """

    // MARK: - Test Images

    /// Generate a simple test image
    static var testImage: UIImage {
        let size = CGSize(width: 100, height: 100)
        UIGraphicsBeginImageContextWithOptions(size, false, 1.0)
        defer { UIGraphicsEndImageContext() }

        UIColor.blue.setFill()
        UIRectFill(CGRect(origin: .zero, size: size))

        return UIGraphicsGetImageFromCurrentImageContext() ?? UIImage()
    }

    /// Generate a test image of specific size
    static func testImage(size: CGSize) -> UIImage {
        UIGraphicsBeginImageContextWithOptions(size, false, 1.0)
        defer { UIGraphicsEndImageContext() }

        UIColor.red.setFill()
        UIRectFill(CGRect(origin: .zero, size: size))

        return UIGraphicsGetImageFromCurrentImageContext() ?? UIImage()
    }

    // MARK: - Wine Results

    /// High confidence wine result
    static let highConfidenceWine = WineResult(
        wineName: "Opus One",
        rating: 4.8,
        confidence: 0.91,
        bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)
    )

    /// Medium confidence wine result
    static let mediumConfidenceWine = WineResult(
        wineName: "La Crema Pinot Noir",
        rating: 4.1,
        confidence: 0.72,
        bbox: BoundingBox(x: 0.35, y: 0.20, width: 0.08, height: 0.30)
    )

    /// Low confidence wine result (visible but not tappable)
    static let lowConfidenceWine = WineResult(
        wineName: "Budget Wine",
        rating: 3.2,
        confidence: 0.55,
        bbox: BoundingBox(x: 0.55, y: 0.25, width: 0.07, height: 0.28)
    )

    /// Hidden wine result (below visibility threshold)
    static let hiddenConfidenceWine = WineResult(
        wineName: "Barely Detected",
        rating: 3.0,
        confidence: 0.40,
        bbox: BoundingBox(x: 0.75, y: 0.30, width: 0.06, height: 0.25)
    )

    // MARK: - Bounding Boxes

    /// Standard bounding box
    static let standardBbox = BoundingBox(x: 0.25, y: 0.40, width: 0.10, height: 0.30)

    /// Partial bottle bounding box (small height)
    static let partialBottleBbox = BoundingBox(x: 0.25, y: 0.80, width: 0.10, height: 0.10)

    /// Edge bounding box (near screen edge)
    static let edgeBbox = BoundingBox(x: 0.95, y: 0.40, width: 0.05, height: 0.30)

    // MARK: - Feedback Payloads

    /// Expected feedback request body (correct match)
    static let correctFeedbackPayload: [String: Any] = [
        "image_id": "test-123",
        "wine_name": "Opus One",
        "is_correct": true,
        "device_id": "test-device-id"
    ]

    /// Expected feedback request body (incorrect match with correction)
    static let incorrectFeedbackPayload: [String: Any] = [
        "image_id": "test-123",
        "wine_name": "Wrong Wine",
        "is_correct": false,
        "corrected_name": "Correct Wine Name",
        "device_id": "test-device-id"
    ]
}

// MARK: - Mock Scan Service

/// Mock scan service for unit testing ScanViewModel
class MockScanServiceForTests: ScanServiceProtocol {
    var scanCallCount = 0
    var lastImage: UIImage?
    var lastDebugFlag: Bool?
    var responseToReturn: ScanResponse?
    var errorToThrow: Error?
    var delay: TimeInterval = 0

    func scan(image: UIImage, debug: Bool, compressionQuality: CGFloat = 0.8) async throws -> ScanResponse {
        scanCallCount += 1
        lastImage = image
        lastDebugFlag = debug

        if delay > 0 {
            try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
        }

        if let error = errorToThrow {
            throw error
        }

        return responseToReturn ?? TestFixtures.fullShelfResponse
    }

    func reset() {
        scanCallCount = 0
        lastImage = nil
        lastDebugFlag = nil
        responseToReturn = nil
        errorToThrow = nil
        delay = 0
    }
}
