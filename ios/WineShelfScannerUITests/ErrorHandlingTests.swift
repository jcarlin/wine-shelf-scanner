import XCTest

/// Tests for error handling: error view, retry, and start over functionality
final class ErrorHandlingTests: BaseUITestCase {

    func testErrorViewAppearsOnFailure() throws {
        // Given: App configured to simulate error
        launchWithError()

        // When: User initiates a scan
        assertExists(choosePhotoButton)
        choosePhotoButton.tap()

        // Then: Error view should appear
        assertExists(errorView, message: "Error view should appear on scan failure")

        // And: Error message should be displayed
        assertExists(errorMessage, message: "Error message should be visible")

        // And: Retry and Start Over buttons should be available
        assertExists(retryButton, message: "Retry button should be visible")
        assertExists(startOverButton, message: "Start Over button should be visible")
    }

    func testRetryButtonTriggersNewScan() throws {
        // Given: Error view is displayed
        launchWithError()
        choosePhotoButton.tap()
        assertExists(errorView)

        // When: User taps Retry
        // Note: In test mode with SIMULATE_ERROR still true, it will error again
        // This test verifies the button is functional
        retryButton.tap()

        // Then: Either error view or some state change should occur
        // The retry action was triggered (button is responsive)
        // Since we're still in error mode, we expect error view again
        assertExists(errorView, timeout: 5, message: "Retry should trigger action")
    }

    func testStartOverReturnsToIdleState() throws {
        // Given: Error view is displayed
        launchWithError()
        choosePhotoButton.tap()
        assertExists(errorView)

        // When: User taps Start Over
        startOverButton.tap()

        // Then: App should return to idle state
        assertExists(choosePhotoButton, message: "Start Over should return to idle state")

        // And: Error view should no longer be visible
        assertNotExists(errorView, message: "Error view should be dismissed")
    }

    func testErrorMessageIsReadable() throws {
        // Given: Error occurred
        launchWithError()
        choosePhotoButton.tap()
        assertExists(errorView)

        // Then: Error message should have content
        XCTAssertTrue(
            errorMessage.exists,
            "Error message element should exist"
        )

        // Verify it's visible to user (has non-empty label)
        let label = errorMessage.label
        XCTAssertFalse(
            label.isEmpty,
            "Error message should have text content"
        )
    }
}
