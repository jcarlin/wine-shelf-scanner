import XCTest

/// Tests for the happy path: photo → results → tap badge → detail sheet
final class HappyPathTests: BaseUITestCase {

    func testFullShelfFlow() throws {
        // Given: App launched with full shelf scenario
        launchWithScenario("full_shelf")

        // When: User taps "Choose Photo" button
        assertExists(choosePhotoButton, message: "Choose Photo button should be visible on idle screen")
        choosePhotoButton.tap()

        // Then: Results view should appear
        assertExists(resultsView, message: "Results view should appear after selecting photo")

        // And: Overlay container should be visible (not fallback list)
        assertExists(overlayContainer, message: "Overlay container should be visible for full shelf")

        // And: New Scan button should be available
        assertExists(newScanButton, message: "New Scan button should be visible")
    }

    func testTapRatingBadgeOpensDetailSheet() throws {
        // Given: App with full shelf results
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // When: User taps a high-confidence wine badge (Opus One has 0.91 confidence)
        let opusOneBadge = ratingBadge(for: "Opus One")
        assertExists(opusOneBadge, message: "Opus One rating badge should exist")
        opusOneBadge.tap()

        // Then: Detail sheet should appear
        assertExists(wineDetailSheet, message: "Detail sheet should appear after tapping badge")

        // And: Wine name should be displayed
        assertExists(detailSheetWineName, message: "Wine name should be in detail sheet")

        // And: Rating should be displayed
        assertExists(detailSheetRating, message: "Rating should be in detail sheet")

        // And: Confidence label should be displayed
        assertExists(detailSheetConfidenceLabel, message: "Confidence label should be in detail sheet")
    }

    func testDismissDetailSheetBySwipe() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        assertExists(caymusBadge)
        caymusBadge.tap()
        assertExists(wineDetailSheet)

        // When: User swipes down to dismiss
        dismissDetailSheet()

        // Then: Detail sheet should disappear
        // Wait a moment for animation
        Thread.sleep(forTimeInterval: 0.5)
        assertNotExists(wineDetailSheet, message: "Detail sheet should be dismissed after swipe")
    }

    func testNewScanReturnsToIdleState() throws {
        // Given: Results are displayed
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // When: User taps "New Scan"
        newScanButton.tap()

        // Then: App should return to idle state with Choose Photo button
        assertExists(choosePhotoButton, message: "Choose Photo button should reappear after New Scan")
    }

    func testMultipleWinesDisplayed() throws {
        // Given: Full shelf with 8 wines
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Multiple rating badges should be visible
        // Check a few known wines from the mock data
        let wines = [
            "Caymus Cabernet Sauvignon",
            "Opus One",
            "Silver Oak Alexander Valley",
            "Jordan Cabernet Sauvignon"
        ]

        for wine in wines {
            let badge = ratingBadge(for: wine)
            XCTAssertTrue(
                badge.waitForExistence(timeout: 2),
                "\(wine) badge should be visible"
            )
        }
    }

    func testTopThreeEmphasis() throws {
        // Given: Full shelf results
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Top 3 rated wines should have badges visible
        // In mock data: Opus One (4.8), Caymus (4.5), Silver Oak (4.4)
        let topThreeWines = [
            "Opus One",
            "Caymus Cabernet Sauvignon",
            "Silver Oak Alexander Valley"
        ]

        for wine in topThreeWines {
            let badge = ratingBadge(for: wine)
            assertExists(badge, message: "\(wine) (top 3) should be visible")
        }
    }
}
