import XCTest
@testable import WineShelfScanner

final class ScanResponseTests: XCTestCase {

    // MARK: - JSON Decoding Tests

    func testDecodingFullShelfResponse() throws {
        let json = """
        {
          "image_id": "test-001",
          "results": [
            {
              "wine_name": "Opus One",
              "rating": 4.8,
              "confidence": 0.91,
              "bbox": { "x": 0.15, "y": 0.12, "width": 0.09, "height": 0.38 }
            }
          ],
          "fallback_list": []
        }
        """
        let data = json.data(using: .utf8)!

        let response = try JSONDecoder().decode(ScanResponse.self, from: data)

        XCTAssertEqual(response.imageId, "test-001")
        XCTAssertEqual(response.results.count, 1)
        XCTAssertEqual(response.results[0].wineName, "Opus One")
        XCTAssertEqual(response.results[0].rating, 4.8 as Double?)
        XCTAssertEqual(response.results[0].confidence, 0.91)
        XCTAssertEqual(response.results[0].bbox.x, 0.15)
        XCTAssertEqual(response.fallbackList.count, 0)
    }

    func testDecodingFallbackList() throws {
        let json = """
        {
          "image_id": "test-002",
          "results": [],
          "fallback_list": [
            { "wine_name": "Caymus", "rating": 4.5 },
            { "wine_name": "Jordan", "rating": 4.3 }
          ]
        }
        """
        let data = json.data(using: .utf8)!

        let response = try JSONDecoder().decode(ScanResponse.self, from: data)

        XCTAssertEqual(response.results.count, 0)
        XCTAssertEqual(response.fallbackList.count, 2)
        XCTAssertEqual(response.fallbackList[0].wineName, "Caymus")
        XCTAssertEqual(response.fallbackList[0].rating, 4.5 as Double?)
    }

    func testDecodingNullRatings() throws {
        let json = """
        {
          "image_id": "test-003",
          "results": [
            {
              "wine_name": "Unknown Wine",
              "rating": null,
              "confidence": 0.75,
              "bbox": { "x": 0.1, "y": 0.2, "width": 0.08, "height": 0.3 }
            }
          ],
          "fallback_list": [
            { "wine_name": "Another Unknown", "rating": null }
          ]
        }
        """
        let data = json.data(using: .utf8)!

        let response = try JSONDecoder().decode(ScanResponse.self, from: data)

        XCTAssertEqual(response.results.count, 1)
        XCTAssertNil(response.results[0].rating)
        XCTAssertEqual(response.results[0].wineName, "Unknown Wine")
        XCTAssertEqual(response.fallbackList.count, 1)
        XCTAssertNil(response.fallbackList[0].rating)
    }

    // MARK: - Computed Properties Tests

    func testTopRatedResults() {
        let response = ScanResponse(
            imageId: "test",
            results: [
                WineResult(wineName: "B", rating: 3.5, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "A", rating: 4.8, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "C", rating: 4.2, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
            ],
            fallbackList: [],
            debug: nil
        )

        let topRated = response.topRatedResults

        XCTAssertEqual(topRated[0].wineName, "A") // 4.8
        XCTAssertEqual(topRated[1].wineName, "C") // 4.2
        XCTAssertEqual(topRated[2].wineName, "B") // 3.5
    }

    func testTopThree() {
        let response = ScanResponse(
            imageId: "test",
            results: [
                WineResult(wineName: "A", rating: 4.8, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "B", rating: 4.5, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "C", rating: 4.2, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "D", rating: 3.5, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
            ],
            fallbackList: [],
            debug: nil
        )

        let topThree = response.topThree

        XCTAssertEqual(topThree.count, 3)
        XCTAssertTrue(response.isTopThree(response.results[0])) // A
        XCTAssertTrue(response.isTopThree(response.results[1])) // B
        XCTAssertTrue(response.isTopThree(response.results[2])) // C
        XCTAssertFalse(response.isTopThree(response.results[3])) // D
    }

    func testVisibleResults() {
        let response = ScanResponse(
            imageId: "test",
            results: [
                WineResult(wineName: "High", rating: 4.8, confidence: 0.90, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "Medium", rating: 4.5, confidence: 0.55, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "Low", rating: 4.2, confidence: 0.40, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
            ],
            fallbackList: [],
            debug: nil
        )

        let visible = response.visibleResults

        XCTAssertEqual(visible.count, 2)
        XCTAssertEqual(visible[0].wineName, "High")
        XCTAssertEqual(visible[1].wineName, "Medium")
    }

    func testTappableResults() {
        let response = ScanResponse(
            imageId: "test",
            results: [
                WineResult(wineName: "Tappable", rating: 4.8, confidence: 0.70, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
                WineResult(wineName: "NotTappable", rating: 4.5, confidence: 0.55, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1)),
            ],
            fallbackList: [],
            debug: nil
        )

        let tappable = response.tappableResults

        XCTAssertEqual(tappable.count, 1)
        XCTAssertEqual(tappable[0].wineName, "Tappable")
    }

    func testPartialDetection() {
        let partial = ScanResponse(
            imageId: "test",
            results: [WineResult(wineName: "A", rating: 4.8, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))],
            fallbackList: [FallbackWine(wineName: "B", rating: 4.5)],
            debug: nil
        )

        let full = ScanResponse(
            imageId: "test",
            results: [WineResult(wineName: "A", rating: 4.8, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))],
            fallbackList: [],
            debug: nil
        )

        XCTAssertTrue(partial.isPartialDetection)
        XCTAssertFalse(full.isPartialDetection)
    }

    func testFullFailure() {
        let failure = ScanResponse(
            imageId: "test",
            results: [],
            fallbackList: [FallbackWine(wineName: "A", rating: 4.5)],
            debug: nil
        )

        let success = ScanResponse(
            imageId: "test",
            results: [WineResult(wineName: "A", rating: 4.8, confidence: 0.9, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))],
            fallbackList: [],
            debug: nil
        )

        XCTAssertTrue(failure.isFullFailure)
        XCTAssertFalse(success.isFullFailure)
    }

    // MARK: - WineResult Tests

    func testConfidenceLabel() {
        let highConfidence = WineResult(wineName: "A", rating: 4.8, confidence: 0.90, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))
        let mediumConfidence = WineResult(wineName: "B", rating: 4.5, confidence: 0.75, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))

        XCTAssertEqual(highConfidence.confidenceLabel, "Widely rated")
        XCTAssertEqual(mediumConfidence.confidenceLabel, "Limited data")
    }

    func testIsTappable() {
        let tappable = WineResult(wineName: "A", rating: 4.8, confidence: 0.70, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))
        let notTappable = WineResult(wineName: "B", rating: 4.5, confidence: 0.60, bbox: BoundingBox(x: 0, y: 0, width: 0.1, height: 0.1))

        XCTAssertTrue(tappable.isTappable)
        XCTAssertFalse(notTappable.isTappable)
    }
}
