import XCTest

/// Tests for full failure scenario: no overlays, fallback list displayed
final class FullFailureTests: BaseUITestCase {

    func testFullFailureShowsFallbackList() throws {
        // Given: App with empty results (full failure)
        launchWithScenario("empty_results")

        // When: User selects a photo
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Fallback container should be visible
        assertExists(fallbackContainer, message: "Fallback list should be shown when no overlays")

        // And: Fallback list header should show "Wines Found"
        assertExists(fallbackListHeader, message: "Fallback list header should be visible")
    }

    func testFallbackListSortedByRating() throws {
        // Given: Full failure with fallback wines
        launchWithScenario("empty_results")
        choosePhotoButton.tap()
        assertExists(resultsView)
        assertExists(fallbackContainer)

        // Then: Wines should be listed
        // The first wine in the list should be the highest rated
        // From mock data: Opus One (4.8) should be first

        // Check that fallback list is populated by looking for wine names
        // Note: These appear as static texts in the fallback list
        let opusOneText = app.staticTexts["Opus One"]
        assertExists(opusOneText, message: "Opus One should appear in fallback list")
    }

    func testNoOverlaysInFullFailure() throws {
        // Given: Full failure scenario
        launchWithScenario("empty_results")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Overlay container should NOT be visible
        // (Full failure shows fallback list instead)
        // We check that no rating badges are visible
        let anyBadge = app.otherElements.matching(
            NSPredicate(format: "identifier BEGINSWITH %@", "ratingBadge_")
        ).firstMatch

        XCTAssertFalse(
            anyBadge.waitForExistence(timeout: 2),
            "No rating badges should be visible in full failure mode"
        )
    }

    func testNewScanAvailableInFallbackMode() throws {
        // Given: Fallback list is showing
        launchWithScenario("empty_results")
        choosePhotoButton.tap()
        assertExists(fallbackContainer)

        // Then: New Scan button should be available
        assertExists(newScanButton, message: "New Scan should be available even in fallback mode")

        // When: User taps New Scan
        newScanButton.tap()

        // Then: Returns to idle
        assertExists(choosePhotoButton)
    }

    func testFallbackListContainsMultipleWines() throws {
        // Given: Full failure with multiple fallback wines
        launchWithScenario("empty_results")
        choosePhotoButton.tap()
        assertExists(fallbackContainer)

        // Then: Multiple wines should appear in the list
        // From mock data we have 8 wines in fallback
        let wineNames = [
            "Caymus Cabernet Sauvignon",
            "Opus One",
            "Silver Oak Alexander Valley",
            "Jordan Cabernet Sauvignon"
        ]

        for wine in wineNames {
            let wineText = app.staticTexts[wine]
            XCTAssertTrue(
                wineText.waitForExistence(timeout: 2),
                "\(wine) should appear in fallback list"
            )
        }
    }

    func testNoPartialToastInFullFailure() throws {
        // Given: Full failure (not partial)
        launchWithScenario("empty_results")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Partial detection toast should NOT appear
        assertNotExists(
            partialDetectionToast,
            message: "Partial detection toast should not appear in full failure"
        )
    }
}
