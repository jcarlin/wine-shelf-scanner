import XCTest
@testable import WineShelfScanner

final class ScanProgressModelTests: XCTestCase {

    // MARK: - Stage Mapping

    func testFindingBottlesAtStart() {
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 0), .findingBottles)
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 2.5), .findingBottles)
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 4.99), .findingBottles)
    }

    func testReadingLabelsFromFiveSeconds() {
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 5), .readingLabels)
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 10), .readingLabels)
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 13.99), .readingLabels)
    }

    func testRankingPicksFromFourteenSeconds() {
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 14), .rankingPicks)
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 30), .rankingPicks)
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: 600), .rankingPicks)
    }

    func testNegativeElapsedIsFindingBottles() {
        // Clock skew should never crash or skip ahead
        XCTAssertEqual(ScanProgressModel.stage(forElapsed: -1), .findingBottles)
    }

    // MARK: - Reassurance Line

    func testReassuranceHiddenBeforeTwentyFiveSeconds() {
        XCTAssertFalse(ScanProgressModel.showsReassurance(forElapsed: 0))
        XCTAssertFalse(ScanProgressModel.showsReassurance(forElapsed: 24.9))
    }

    func testReassuranceShownFromTwentyFiveSeconds() {
        XCTAssertTrue(ScanProgressModel.showsReassurance(forElapsed: 25))
        XCTAssertTrue(ScanProgressModel.showsReassurance(forElapsed: 120))
    }

    // MARK: - Localization

    func testStageTextsAreLocalizedAndDistinct() {
        let texts = [
            ScanProgressStage.findingBottles.localizedText,
            ScanProgressStage.readingLabels.localizedText,
            ScanProgressStage.rankingPicks.localizedText,
        ]
        // Resolved strings must not be raw keys
        for text in texts {
            XCTAssertFalse(text.hasPrefix("processing."), "Unresolved localization key: \(text)")
            XCTAssertFalse(text.isEmpty)
        }
        XCTAssertEqual(Set(texts).count, 3, "Stage texts should be distinct")
    }
}
