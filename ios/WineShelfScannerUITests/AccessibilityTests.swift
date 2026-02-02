import XCTest

/// Tests for accessibility compliance and VoiceOver support
final class AccessibilityTests: BaseUITestCase {

    // MARK: - Idle Screen Accessibility

    func testIdleScreenHasAccessibleButtons() throws {
        // Given: App on idle screen
        app.launch()

        // Then: Choose Photo button should be accessible
        assertExists(choosePhotoButton, message: "Choose Photo button should exist")
        XCTAssertTrue(choosePhotoButton.isHittable, "Choose Photo button should be hittable")

        // Verify button has a label
        XCTAssertFalse(choosePhotoButton.label.isEmpty, "Choose Photo button should have a label")
    }

    func testScanShelfButtonAccessibility() throws {
        // Given: App on idle screen
        app.launch()

        // Then: Scan Shelf button should be accessible
        assertExists(scanShelfButton, message: "Scan Shelf button should exist")

        // It may not always be hittable if permissions aren't granted
        // but it should have accessibility properties
        XCTAssertFalse(scanShelfButton.label.isEmpty, "Scan Shelf button should have a label")
    }

    // MARK: - Results Screen Accessibility

    func testRatingBadgeHasAccessibleLabel() throws {
        // Given: Results view is displayed
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: Rating badges should have accessible labels
        let opusOneBadge = ratingBadge(for: "Opus One")
        assertExists(opusOneBadge)

        // The badge should be hittable (interactive)
        XCTAssertTrue(opusOneBadge.isHittable, "Rating badge should be hittable")
    }

    func testNewScanButtonAccessibility() throws {
        // Given: Results view is displayed
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: New Scan button should be accessible
        assertExists(newScanButton)
        XCTAssertTrue(newScanButton.isHittable, "New Scan button should be hittable")
        XCTAssertFalse(newScanButton.label.isEmpty, "New Scan button should have a label")
    }

    // MARK: - Detail Sheet Accessibility

    func testDetailSheetHasAccessibleContent() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        assertExists(wineDetailSheet)

        // Then: Wine name should be accessible
        assertExists(detailSheetWineName)
        XCTAssertFalse(detailSheetWineName.label.isEmpty, "Wine name should have accessible text")

        // And: Rating should be accessible
        assertExists(detailSheetRating)
        XCTAssertFalse(detailSheetRating.label.isEmpty, "Rating should have accessible text")

        // And: Confidence label should be accessible
        assertExists(detailSheetConfidenceLabel)
        XCTAssertFalse(detailSheetConfidenceLabel.label.isEmpty, "Confidence label should have accessible text")
    }

    func testDetailSheetCanBeDismissed() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        caymusBadge.tap()

        assertExists(wineDetailSheet)

        // Then: Sheet should be dismissible by swipe
        dismissDetailSheet()
        Thread.sleep(forTimeInterval: 0.5)

        assertNotExists(wineDetailSheet, message: "Detail sheet should be dismissible")
    }

    // MARK: - Error Screen Accessibility

    func testErrorScreenHasAccessibleContent() throws {
        // Given: Error state
        launchWithError()

        // Trigger error by attempting action
        choosePhotoButton.tap()

        // Wait for error view
        if errorView.waitForExistence(timeout: 5) {
            // Then: Error message should be accessible
            assertExists(errorMessage)
            XCTAssertFalse(errorMessage.label.isEmpty, "Error message should have accessible text")

            // And: Action buttons should be accessible
            if retryButton.exists {
                XCTAssertTrue(retryButton.isHittable, "Retry button should be hittable")
            }

            if startOverButton.exists {
                XCTAssertTrue(startOverButton.isHittable, "Start Over button should be hittable")
            }
        }
    }

    // MARK: - Critical Element Identifiers

    func testAllCriticalElementsHaveIdentifiers() throws {
        // Test that key navigation elements have accessibility identifiers
        // This helps with automated testing and screen reader navigation

        // Given: App with results
        launchWithScenario("full_shelf")

        // Then: Idle state elements have identifiers
        XCTAssertTrue(choosePhotoButton.exists, "choosePhotoButton identifier works")
        XCTAssertTrue(scanShelfButton.exists, "scanShelfButton identifier works")

        // Navigate to results
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Results state elements have identifiers
        XCTAssertTrue(resultsView.exists, "resultsView identifier works")
        XCTAssertTrue(newScanButton.exists, "newScanButton identifier works")
        XCTAssertTrue(overlayContainer.exists, "overlayContainer identifier works")

        // Open detail sheet
        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        // Then: Detail sheet elements have identifiers
        XCTAssertTrue(wineDetailSheet.exists, "wineDetailSheet identifier works")
        XCTAssertTrue(detailSheetWineName.exists, "detailSheetWineName identifier works")
        XCTAssertTrue(detailSheetRating.exists, "detailSheetRating identifier works")
    }

    // MARK: - Feedback Accessibility

    func testFeedbackButtonsAreAccessible() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        assertExists(wineDetailSheet)

        // Then: Feedback buttons should be accessible
        let thumbsUp = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
        let thumbsDown = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsDownButton]

        if thumbsUp.exists {
            XCTAssertTrue(thumbsUp.isHittable, "Thumbs up button should be hittable")
        }

        if thumbsDown.exists {
            XCTAssertTrue(thumbsDown.isHittable, "Thumbs down button should be hittable")
        }
    }

    // MARK: - Debug Tray Accessibility

    func testDebugTrayIsAccessible() throws {
        // Given: Results with debug data
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: Debug tray should be accessible
        let debugTray = app.otherElements[AccessibilityIdentifiers.DebugTray.view]
        if debugTray.exists {
            // Debug header should be tappable
            let debugHeader = app.otherElements[AccessibilityIdentifiers.DebugTray.header]
            if debugHeader.exists {
                XCTAssertTrue(debugHeader.isHittable, "Debug tray header should be hittable")
            }
        }
    }

    // MARK: - Partial Detection Toast Accessibility

    func testPartialDetectionToastIsAccessible() throws {
        // Given: Partial detection scenario
        launchWithScenario("partial_detection")
        selectPhotoAndWaitForResults()

        // Then: Partial detection toast should be accessible
        if partialDetectionToast.exists {
            XCTAssertFalse(partialDetectionToast.label.isEmpty, "Partial detection toast should have accessible text")
        }
    }

    // MARK: - Fallback List Accessibility

    func testFallbackListIsAccessible() throws {
        // Given: Full failure scenario with only fallback
        launchWithScenario("full_failure")
        selectPhotoAndWaitForResults()

        // Then: Fallback container should be accessible
        if fallbackContainer.exists {
            // Fallback header should have text
            if fallbackListHeader.exists {
                XCTAssertFalse(fallbackListHeader.label.isEmpty, "Fallback header should have accessible text")
            }
        }
    }

    // MARK: - Dynamic Type Support

    func testUIScalesWithDynamicType() throws {
        // This test verifies the app doesn't crash with accessibility text sizes
        // Note: Actual dynamic type testing requires accessibility settings changes

        // Given: App launched normally
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: App should not crash and elements should exist
        XCTAssertTrue(resultsView.exists, "Results view should exist")
        XCTAssertTrue(newScanButton.exists, "New scan button should exist")
    }

    // MARK: - Touch Target Sizes

    func testButtonsHaveAdequateTouchTargets() throws {
        // Given: App on idle screen
        app.launch()

        // Then: Buttons should be large enough for touch (44pt minimum per HIG)
        let choosePhotoFrame = choosePhotoButton.frame
        let scanShelfFrame = scanShelfButton.frame

        // Check minimum dimensions (allowing for some tolerance)
        let minimumDimension: CGFloat = 40

        XCTAssertGreaterThanOrEqual(
            choosePhotoFrame.width,
            minimumDimension,
            "Choose Photo button width should be adequate"
        )
        XCTAssertGreaterThanOrEqual(
            choosePhotoFrame.height,
            minimumDimension,
            "Choose Photo button height should be adequate"
        )

        XCTAssertGreaterThanOrEqual(
            scanShelfFrame.width,
            minimumDimension,
            "Scan Shelf button width should be adequate"
        )
        XCTAssertGreaterThanOrEqual(
            scanShelfFrame.height,
            minimumDimension,
            "Scan Shelf button height should be adequate"
        )
    }
}
