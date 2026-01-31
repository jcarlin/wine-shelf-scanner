import XCTest

/// Tests for partial detection scenario: some wines detected, some in fallback
final class PartialDetectionTests: BaseUITestCase {

    func testPartialDetectionShowsToast() throws {
        // Given: App with partial detection scenario
        launchWithScenario("partial_detection")

        // When: User selects a photo
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Toast message should appear
        assertExists(
            partialDetectionToast,
            timeout: 2,
            message: "Toast should appear for partial detection"
        )
    }

    func testPartialDetectionShowsSomeOverlays() throws {
        // Given: Partial detection (3 wines with overlays)
        launchWithScenario("partial_detection")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Overlay container should be visible (not fallback-only mode)
        assertExists(overlayContainer, message: "Overlays should be shown for partial detection")

        // And: The detected wines should have badges
        // From mock: Caymus, Opus One, Silver Oak
        let detectedWines = [
            "Caymus Cabernet Sauvignon",
            "Opus One",
            "Silver Oak Alexander Valley"
        ]

        for wine in detectedWines {
            let badge = ratingBadge(for: wine)
            assertExists(badge, message: "\(wine) should have a visible badge")
        }
    }

    func testPartialDetectionWinesAreTappable() throws {
        // Given: Partial detection results
        launchWithScenario("partial_detection")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // When: User taps a detected wine badge
        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        assertExists(caymusBadge)
        caymusBadge.tap()

        // Then: Detail sheet should open
        assertExists(wineDetailSheet, message: "Detail sheet should open for detected wine")
    }

    func testToastAutoDismisses() throws {
        // Given: Partial detection with toast
        launchWithScenario("partial_detection")
        choosePhotoButton.tap()
        assertExists(partialDetectionToast, timeout: 2)

        // When: Waiting for auto-dismiss (3 seconds in implementation)
        // Wait longer than the 3 second auto-dismiss
        Thread.sleep(forTimeInterval: 4)

        // Then: Toast should be dismissed
        assertNotExists(partialDetectionToast, message: "Toast should auto-dismiss after 3 seconds")
    }

    func testPartialDetectionStillShowsNewScan() throws {
        // Given: Partial detection results
        launchWithScenario("partial_detection")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: New Scan button should still be available
        assertExists(newScanButton, message: "New Scan button should be available")
    }
}
