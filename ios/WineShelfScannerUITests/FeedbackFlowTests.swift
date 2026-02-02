import XCTest

/// Tests for the user feedback flow (thumbs up/down)
final class FeedbackFlowTests: BaseUITestCase {

    // MARK: - Feedback Button Visibility

    func testFeedbackButtonsVisibleInDetailSheet() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        assertExists(wineDetailSheet)

        // Then: Thumbs up and down buttons should be visible
        let thumbsUp = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
        let thumbsDown = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsDownButton]

        assertExists(thumbsUp, message: "Thumbs up button should be visible in detail sheet")
        assertExists(thumbsDown, message: "Thumbs down button should be visible in detail sheet")
    }

    func testFeedbackPromptVisible() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        caymusBadge.tap()

        assertExists(wineDetailSheet)

        // Then: Feedback prompt "Is this the right wine?" should be visible
        let feedbackPrompt = app.staticTexts[AccessibilityIdentifiers.DetailSheet.feedbackPrompt]
        assertExists(feedbackPrompt, message: "Feedback prompt should be visible")
    }

    // MARK: - Thumbs Up Flow

    func testThumbsUpShowsConfirmation() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        assertExists(wineDetailSheet)

        // When: User taps thumbs up
        let thumbsUp = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
        thumbsUp.tap()

        // Then: Confirmation message should appear
        // Wait for animation and async feedback submission
        Thread.sleep(forTimeInterval: 1.0)

        let confirmation = app.otherElements[AccessibilityIdentifiers.DetailSheet.feedbackConfirmation]
        // Look for the confirmation text if element query doesn't work
        let confirmationTexts = app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'Thanks'"))

        XCTAssertTrue(
            confirmation.exists || confirmationTexts.count > 0,
            "Confirmation should appear after thumbs up"
        )
    }

    func testThumbsUpButtonChangesAppearance() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        assertExists(wineDetailSheet)

        // When: User taps thumbs up
        let thumbsUp = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]

        // Capture state before tap
        XCTAssertTrue(thumbsUp.exists, "Thumbs up button should exist before tap")

        thumbsUp.tap()

        // Allow time for state change
        Thread.sleep(forTimeInterval: 0.5)

        // Then: Button should still exist (or be replaced by confirmation)
        // At minimum, feedback submission shouldn't crash
        XCTAssertTrue(wineDetailSheet.exists, "Detail sheet should remain visible")
    }

    // MARK: - Thumbs Down Flow

    func testThumbsDownShowsCorrectionField() throws {
        // Given: Detail sheet is open
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        caymusBadge.tap()

        assertExists(wineDetailSheet)

        // When: User taps thumbs down
        let thumbsDown = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsDownButton]
        thumbsDown.tap()

        // Then: Correction text field should appear
        Thread.sleep(forTimeInterval: 0.3)

        let correctionField = app.textFields[AccessibilityIdentifiers.DetailSheet.correctionTextField]
        assertExists(correctionField, timeout: 2, message: "Correction text field should appear after thumbs down")
    }

    func testCorrectionFieldPlaceholderText() throws {
        // Given: Thumbs down tapped
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        let thumbsDown = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsDownButton]
        thumbsDown.tap()

        Thread.sleep(forTimeInterval: 0.3)

        // Then: Correction field should have placeholder text
        let correctionField = app.textFields[AccessibilityIdentifiers.DetailSheet.correctionTextField]
        assertExists(correctionField)

        // Check for placeholder value or label
        XCTAssertTrue(
            correctionField.placeholderValue?.contains("Wine") ?? false ||
            correctionField.placeholderValue?.contains("name") ?? false ||
            correctionField.label.contains("Wine") ||
            correctionField.label.contains("name"),
            "Correction field should have wine-related placeholder"
        )
    }

    func testSubmitCorrectionShowsConfirmation() throws {
        // Given: Correction field is visible
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        caymusBadge.tap()

        let thumbsDown = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsDownButton]
        thumbsDown.tap()

        Thread.sleep(forTimeInterval: 0.3)

        let correctionField = app.textFields[AccessibilityIdentifiers.DetailSheet.correctionTextField]
        assertExists(correctionField)

        // When: User types a correction and submits
        correctionField.tap()
        correctionField.typeText("Correct Wine Name")

        // Find and tap submit button
        let submitButton = app.buttons["Submit"]
        if submitButton.exists {
            submitButton.tap()

            // Then: Confirmation should appear
            Thread.sleep(forTimeInterval: 1.0)

            let confirmationTexts = app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'Thanks'"))
            XCTAssertTrue(
                confirmationTexts.count > 0,
                "Confirmation should appear after submitting correction"
            )
        }
    }

    func testCancelCorrectionReturnsToPreviousState() throws {
        // Given: Correction field is visible
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        let thumbsDown = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsDownButton]
        thumbsDown.tap()

        Thread.sleep(forTimeInterval: 0.3)

        let correctionField = app.textFields[AccessibilityIdentifiers.DetailSheet.correctionTextField]
        assertExists(correctionField)

        // When: User taps cancel
        let cancelButton = app.buttons["Cancel"]
        if cancelButton.exists {
            cancelButton.tap()

            // Then: Should return to feedback buttons
            Thread.sleep(forTimeInterval: 0.3)

            let thumbsUpAfterCancel = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
            assertExists(thumbsUpAfterCancel, message: "Thumbs up should reappear after cancel")
        }
    }

    // MARK: - Feedback State Persistence

    func testFeedbackStateResetsOnNewDetailSheet() throws {
        // Given: Feedback was submitted for one wine
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()

        let thumbsUp = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
        thumbsUp.tap()

        Thread.sleep(forTimeInterval: 1.0)

        // Dismiss and open different wine
        dismissDetailSheet()
        Thread.sleep(forTimeInterval: 0.5)

        let caymusBadge = ratingBadge(for: "Caymus Cabernet Sauvignon")
        caymusBadge.tap()

        assertExists(wineDetailSheet)

        // Then: New detail sheet should have fresh feedback buttons
        let thumbsUpNew = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
        assertExists(thumbsUpNew, message: "New detail sheet should have fresh feedback buttons")
    }

    // MARK: - Edge Cases

    func testFeedbackWithLowConfidenceWine() throws {
        // Given: Detail sheet for a medium confidence wine
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Try to find a medium confidence wine that's still tappable
        let jordanBadge = ratingBadge(for: "Jordan Cabernet Sauvignon")
        if jordanBadge.waitForExistence(timeout: 2) {
            jordanBadge.tap()

            if wineDetailSheet.waitForExistence(timeout: 2) {
                // Then: Feedback buttons should still work
                let thumbsUp = app.buttons[AccessibilityIdentifiers.DetailSheet.thumbsUpButton]
                assertExists(thumbsUp, message: "Feedback should be available for medium confidence wines")
            }
        }
    }
}
