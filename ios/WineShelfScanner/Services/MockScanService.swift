import UIKit

/// Mock scan service for development and testing
class MockScanService: ScanServiceProtocol {
    /// Which mock scenario to return
    var scenario: MockScenario = .fullShelf

    /// Simulated network delay
    var simulatedDelay: TimeInterval = 0.5

    /// Whether to simulate an error
    var shouldSimulateError: Bool = false
    var errorToSimulate: ScanError = .networkError(NSError(domain: "", code: -1))

    enum MockScenario: String, CaseIterable {
        case fullShelf = "full_shelf"
        case partialDetection = "partial_detection"
        case lowConfidence = "low_confidence"
        case emptyResults = "empty_results"
    }

    func scan(image: UIImage, debug: Bool = false) async throws -> ScanResponse {
        // Simulate network delay
        try await Task.sleep(nanoseconds: UInt64(simulatedDelay * 1_000_000_000))

        // Simulate error if configured
        if shouldSimulateError {
            throw errorToSimulate
        }

        // Return mock response (with mock debug data if requested)
        var response = mockResponse(for: scenario)
        if debug {
            response = addMockDebugData(to: response)
        }
        return response
    }

    private func addMockDebugData(to response: ScanResponse) -> ScanResponse {
        let mockSteps = response.results.enumerated().map { index, result in
            DebugPipelineStep(
                rawText: "MOCK OCR TEXT FOR \(result.wineName.uppercased())",
                normalizedText: result.wineName.lowercased(),
                bottleIndex: index,
                fuzzyMatch: FuzzyMatchDebug(
                    candidate: result.wineName,
                    scores: FuzzyMatchScores(
                        ratio: 0.85,
                        partialRatio: 0.92,
                        tokenSortRatio: 0.88,
                        phoneticBonus: 0.05,
                        weightedScore: result.confidence
                    ),
                    rating: result.rating
                ),
                llmValidation: result.confidence < 0.85 ? LLMValidationDebug(
                    isValidMatch: true,
                    wineName: result.wineName,
                    confidence: result.confidence,
                    reasoning: "Mock: LLM confirmed match"
                ) : nil,
                finalResult: DebugFinalResult(
                    wineName: result.wineName,
                    confidence: result.confidence,
                    source: result.confidence >= 0.85 ? "database" : "llm"
                ),
                stepFailed: nil,
                includedInResults: true
            )
        }

        let debugData = DebugData(
            pipelineSteps: mockSteps,
            totalOcrTexts: response.results.count + 2,
            bottlesDetected: response.results.count,
            textsMatched: response.results.count,
            llmCallsMade: mockSteps.filter { $0.llmValidation != nil }.count > 0 ? 1 : 0
        )

        return ScanResponse(
            imageId: response.imageId,
            results: response.results,
            fallbackList: response.fallbackList,
            debug: debugData
        )
    }

    // MARK: - Mock Data

    private func mockResponse(for scenario: MockScenario) -> ScanResponse {
        switch scenario {
        case .fullShelf:
            return fullShelfResponse()
        case .partialDetection:
            return partialDetectionResponse()
        case .lowConfidence:
            return lowConfidenceResponse()
        case .emptyResults:
            return emptyResultsResponse()
        }
    }

    private func fullShelfResponse() -> ScanResponse {
        ScanResponse(
            imageId: "mock-\(UUID().uuidString.prefix(8))",
            results: [
                WineResult(
                    wineName: "Caymus Cabernet Sauvignon",
                    rating: 4.5,
                    confidence: 0.94,
                    bbox: BoundingBox(x: 0.05, y: 0.15, width: 0.08, height: 0.35)
                ),
                WineResult(
                    wineName: "Opus One",
                    rating: 4.8,
                    confidence: 0.91,
                    bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)
                ),
                WineResult(
                    wineName: "Silver Oak Alexander Valley",
                    rating: 4.4,
                    confidence: 0.88,
                    bbox: BoundingBox(x: 0.26, y: 0.14, width: 0.08, height: 0.36)
                ),
                WineResult(
                    wineName: "Jordan Cabernet Sauvignon",
                    rating: 4.3,
                    confidence: 0.85,
                    bbox: BoundingBox(x: 0.36, y: 0.13, width: 0.08, height: 0.37)
                ),
                WineResult(
                    wineName: "Kendall-Jackson Vintner's Reserve",
                    rating: 3.8,
                    confidence: 0.79,
                    bbox: BoundingBox(x: 0.46, y: 0.16, width: 0.08, height: 0.34)
                ),
                WineResult(
                    wineName: "La Crema Sonoma Coast Pinot Noir",
                    rating: 4.1,
                    confidence: 0.72,
                    bbox: BoundingBox(x: 0.56, y: 0.14, width: 0.08, height: 0.36)
                ),
                WineResult(
                    wineName: "Meiomi Pinot Noir",
                    rating: 3.9,
                    confidence: 0.68,
                    bbox: BoundingBox(x: 0.66, y: 0.15, width: 0.08, height: 0.35)
                ),
                WineResult(
                    wineName: "Bread & Butter Chardonnay",
                    rating: 3.7,
                    confidence: 0.52,
                    bbox: BoundingBox(x: 0.76, y: 0.17, width: 0.08, height: 0.33)
                ),
            ],
            fallbackList: [],
            debug: nil
        )
    }

    private func partialDetectionResponse() -> ScanResponse {
        ScanResponse(
            imageId: "mock-\(UUID().uuidString.prefix(8))",
            results: [
                WineResult(
                    wineName: "Caymus Cabernet Sauvignon",
                    rating: 4.5,
                    confidence: 0.92,
                    bbox: BoundingBox(x: 0.10, y: 0.15, width: 0.10, height: 0.35)
                ),
                WineResult(
                    wineName: "Opus One",
                    rating: 4.8,
                    confidence: 0.89,
                    bbox: BoundingBox(x: 0.30, y: 0.12, width: 0.10, height: 0.38)
                ),
                WineResult(
                    wineName: "Silver Oak Alexander Valley",
                    rating: 4.4,
                    confidence: 0.86,
                    bbox: BoundingBox(x: 0.50, y: 0.14, width: 0.10, height: 0.36)
                ),
            ],
            fallbackList: [
                FallbackWine(wineName: "Jordan Cabernet Sauvignon", rating: 4.3),
                FallbackWine(wineName: "Kendall-Jackson Vintner's Reserve", rating: 3.8),
                FallbackWine(wineName: "La Crema Sonoma Coast Pinot Noir", rating: 4.1),
                FallbackWine(wineName: "Meiomi Pinot Noir", rating: 3.9),
                FallbackWine(wineName: "Bread & Butter Chardonnay", rating: 3.7),
            ],
            debug: nil
        )
    }

    private func lowConfidenceResponse() -> ScanResponse {
        ScanResponse(
            imageId: "mock-\(UUID().uuidString.prefix(8))",
            results: [
                WineResult(
                    wineName: "Unknown Red Wine",
                    rating: 3.5,
                    confidence: 0.58,
                    bbox: BoundingBox(x: 0.10, y: 0.15, width: 0.12, height: 0.35)
                ),
                WineResult(
                    wineName: "Unknown White Wine",
                    rating: 3.3,
                    confidence: 0.52,
                    bbox: BoundingBox(x: 0.30, y: 0.12, width: 0.12, height: 0.38)
                ),
                WineResult(
                    wineName: "Unknown Rose",
                    rating: 3.6,
                    confidence: 0.48,
                    bbox: BoundingBox(x: 0.50, y: 0.14, width: 0.12, height: 0.36)
                ),
                WineResult(
                    wineName: "Unknown Sparkling",
                    rating: 3.4,
                    confidence: 0.41,
                    bbox: BoundingBox(x: 0.70, y: 0.13, width: 0.12, height: 0.37)
                ),
            ],
            fallbackList: [
                FallbackWine(wineName: "Possible Cabernet", rating: 3.8),
                FallbackWine(wineName: "Possible Chardonnay", rating: 3.5),
            ],
            debug: nil
        )
    }

    private func emptyResultsResponse() -> ScanResponse {
        ScanResponse(
            imageId: "mock-\(UUID().uuidString.prefix(8))",
            results: [],
            fallbackList: [
                FallbackWine(wineName: "Caymus Cabernet Sauvignon", rating: 4.5),
                FallbackWine(wineName: "Opus One", rating: 4.8),
                FallbackWine(wineName: "Silver Oak Alexander Valley", rating: 4.4),
                FallbackWine(wineName: "Jordan Cabernet Sauvignon", rating: 4.3),
                FallbackWine(wineName: "La Crema Sonoma Coast Pinot Noir", rating: 4.1),
                FallbackWine(wineName: "Meiomi Pinot Noir", rating: 3.9),
                FallbackWine(wineName: "Kendall-Jackson Vintner's Reserve", rating: 3.8),
                FallbackWine(wineName: "Bread & Butter Chardonnay", rating: 3.7),
            ],
            debug: nil
        )
    }
}
