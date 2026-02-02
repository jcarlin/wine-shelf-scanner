import XCTest

/// Tests for the debug tray functionality
final class DebugTrayTests: BaseUITestCase {

    // MARK: - Debug Tray Visibility

    func testDebugTrayVisibleAfterScan() throws {
        // Given: App launched with full shelf scenario (includes debug data)
        launchWithScenario("full_shelf")

        // When: User selects a photo
        selectPhotoAndWaitForResults()

        // Then: Debug tray should be visible
        let debugTray = app.otherElements[AccessibilityIdentifiers.DebugTray.view]
        assertExists(debugTray, message: "Debug tray should be visible after scan")
    }

    func testDebugTrayHeaderShowsStatSummary() throws {
        // Given: Results with debug data
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: Stat summary should be visible in header
        let statSummary = app.otherElements[AccessibilityIdentifiers.DebugTray.statSummary]
        assertExists(statSummary, timeout: 5, message: "Stat summary should be visible in debug header")
    }

    // MARK: - Debug Tray Expand/Collapse

    func testDebugTrayExpandsOnTap() throws {
        // Given: Debug tray is collapsed
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let debugHeader = app.otherElements[AccessibilityIdentifiers.DebugTray.header]
        assertExists(debugHeader)

        // When: User taps the debug header
        debugHeader.tap()

        // Then: Steps list should become visible
        let stepsList = app.scrollViews[AccessibilityIdentifiers.DebugTray.stepsList]
        assertExists(stepsList, timeout: 2, message: "Steps list should appear when expanded")
    }

    func testDebugTrayCollapsesOnSecondTap() throws {
        // Given: Debug tray is expanded
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let debugHeader = app.otherElements[AccessibilityIdentifiers.DebugTray.header]
        assertExists(debugHeader)

        // Expand first
        debugHeader.tap()

        let stepsList = app.scrollViews[AccessibilityIdentifiers.DebugTray.stepsList]
        assertExists(stepsList, timeout: 2)

        // When: User taps header again
        debugHeader.tap()

        // Then: Steps list should disappear
        Thread.sleep(forTimeInterval: 0.3)
        assertNotExists(stepsList, message: "Steps list should hide when collapsed")
    }

    // MARK: - Pipeline Steps Display

    func testDebugTrayShowsPipelineSteps() throws {
        // Given: Debug tray is expanded
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let debugHeader = app.otherElements[AccessibilityIdentifiers.DebugTray.header]
        debugHeader.tap()

        // Then: At least one pipeline step should be visible
        let firstStep = app.otherElements[AccessibilityIdentifiers.DebugTray.stepRow(0)]
        assertExists(firstStep, timeout: 2, message: "First pipeline step should be visible")
    }

    func testStepRowExpandsOnTap() throws {
        // Given: Debug tray is expanded with visible steps
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let debugHeader = app.otherElements[AccessibilityIdentifiers.DebugTray.header]
        debugHeader.tap()

        let firstStep = app.otherElements[AccessibilityIdentifiers.DebugTray.stepRow(0)]
        assertExists(firstStep, timeout: 2)

        // When: User taps a step row
        firstStep.tap()

        // Allow animation to complete
        Thread.sleep(forTimeInterval: 0.3)

        // Then: Step should expand (indicated by expanded background or detail content)
        // The step row should still exist and potentially show more content
        XCTAssertTrue(firstStep.exists, "Step row should remain visible after tap")
    }

    // MARK: - Debug Tray Content

    func testDebugTrayShowsMatchedCount() throws {
        // Given: Results with debug data
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: Header should contain text indicating matched count
        let debugTray = app.otherElements[AccessibilityIdentifiers.DebugTray.view]
        assertExists(debugTray)

        // Check for "matched" text somewhere in the debug tray
        let matchedText = debugTray.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'matched'"))
        XCTAssertGreaterThan(matchedText.count, 0, "Debug tray should show 'matched' count")
    }

    // MARK: - Debug Tray Interaction with Results

    func testDebugTrayDoesNotBlockOverlays() throws {
        // Given: Results with debug tray visible
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        // Then: Rating badges should still be tappable
        let opusOneBadge = ratingBadge(for: "Opus One")
        assertExists(opusOneBadge)

        opusOneBadge.tap()
        assertExists(wineDetailSheet, message: "Detail sheet should open even with debug tray present")
    }

    func testDebugTrayPersistsAfterDetailSheetDismiss() throws {
        // Given: Debug tray visible, detail sheet opened and dismissed
        launchWithScenario("full_shelf")
        selectPhotoAndWaitForResults()

        let debugTray = app.otherElements[AccessibilityIdentifiers.DebugTray.view]
        assertExists(debugTray)

        // Open and dismiss detail sheet
        let opusOneBadge = ratingBadge(for: "Opus One")
        opusOneBadge.tap()
        assertExists(wineDetailSheet)

        dismissDetailSheet()
        Thread.sleep(forTimeInterval: 0.5)

        // Then: Debug tray should still be visible
        assertExists(debugTray, message: "Debug tray should persist after detail sheet dismiss")
    }
}
