import XCTest

/// Base class for Wine Shelf Scanner UI tests
/// Provides common setup, launch configuration, and helper methods
class BaseUITestCase: XCTestCase {

    var app: XCUIApplication!

    /// Default timeout for element waits
    let defaultTimeout: TimeInterval = 10

    override func setUpWithError() throws {
        try super.setUpWithError()
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
        app = nil
        try super.tearDownWithError()
    }

    // MARK: - Launch Helpers

    /// Launch the app with a specific mock scenario
    /// - Parameter scenario: The mock scenario to use (from MockScanService.MockScenario)
    func launchWithScenario(_ scenario: String) {
        app.launchEnvironment["USE_MOCKS"] = "true"
        app.launchEnvironment["MOCK_SCENARIO"] = scenario
        app.launch()
    }

    /// Launch the app configured to simulate an error
    func launchWithError() {
        app.launchEnvironment["USE_MOCKS"] = "true"
        app.launchEnvironment["SIMULATE_ERROR"] = "true"
        app.launch()
    }

    /// Launch the app in normal mode (no mocks)
    func launchNormal() {
        app.launch()
    }

    // MARK: - Wait Helpers

    /// Wait for an element to exist
    /// - Parameters:
    ///   - element: The element to wait for
    ///   - timeout: Maximum time to wait (defaults to defaultTimeout)
    /// - Returns: Whether the element exists
    @discardableResult
    func waitForElement(_ element: XCUIElement, timeout: TimeInterval? = nil) -> Bool {
        element.waitForExistence(timeout: timeout ?? defaultTimeout)
    }

    /// Wait for an element to exist and assert it does
    /// - Parameters:
    ///   - element: The element to wait for
    ///   - timeout: Maximum time to wait
    ///   - message: Failure message
    func assertExists(
        _ element: XCUIElement,
        timeout: TimeInterval? = nil,
        message: String? = nil
    ) {
        let exists = waitForElement(element, timeout: timeout)
        XCTAssertTrue(exists, message ?? "Element \(element) should exist")
    }

    /// Wait for an element to not exist
    /// - Parameters:
    ///   - element: The element to wait for disappearance
    ///   - timeout: Maximum time to wait
    func assertNotExists(
        _ element: XCUIElement,
        timeout: TimeInterval? = nil,
        message: String? = nil
    ) {
        let exists = element.waitForExistence(timeout: timeout ?? 2)
        XCTAssertFalse(exists, message ?? "Element \(element) should not exist")
    }

    // MARK: - Element Accessors

    /// Get the "Choose Photo" button on idle screen
    var choosePhotoButton: XCUIElement {
        app.buttons[AccessibilityIdentifiers.Idle.choosePhotoButton]
    }

    /// Get the "Scan Shelf" camera button on idle screen
    var scanShelfButton: XCUIElement {
        app.buttons[AccessibilityIdentifiers.Idle.scanShelfButton]
    }

    /// Get the processing spinner
    var processingSpinner: XCUIElement {
        app.activityIndicators[AccessibilityIdentifiers.Processing.spinner]
    }

    /// Get the results view
    var resultsView: XCUIElement {
        app.otherElements[AccessibilityIdentifiers.Results.view]
    }

    /// Get the overlay container
    var overlayContainer: XCUIElement {
        app.otherElements[AccessibilityIdentifiers.Results.overlayContainer]
    }

    /// Get the "New Scan" button
    var newScanButton: XCUIElement {
        app.buttons[AccessibilityIdentifiers.Results.newScanButton]
    }

    /// Get the partial detection toast
    var partialDetectionToast: XCUIElement {
        app.staticTexts[AccessibilityIdentifiers.Results.partialDetectionToast]
    }

    /// Get the fallback list container
    var fallbackContainer: XCUIElement {
        app.otherElements[AccessibilityIdentifiers.Results.fallbackContainer]
    }

    /// Get the fallback list header
    var fallbackListHeader: XCUIElement {
        app.staticTexts[AccessibilityIdentifiers.Results.fallbackListHeader]
    }

    /// Get the wine detail sheet
    var wineDetailSheet: XCUIElement {
        app.otherElements[AccessibilityIdentifiers.DetailSheet.view]
    }

    /// Get the detail sheet wine name
    var detailSheetWineName: XCUIElement {
        app.staticTexts[AccessibilityIdentifiers.DetailSheet.wineName]
    }

    /// Get the detail sheet rating
    var detailSheetRating: XCUIElement {
        app.staticTexts[AccessibilityIdentifiers.DetailSheet.rating]
    }

    /// Get the detail sheet confidence label
    var detailSheetConfidenceLabel: XCUIElement {
        app.staticTexts[AccessibilityIdentifiers.DetailSheet.confidenceLabel]
    }

    /// Get the error view
    var errorView: XCUIElement {
        app.otherElements[AccessibilityIdentifiers.Error.view]
    }

    /// Get the error message
    var errorMessage: XCUIElement {
        app.staticTexts[AccessibilityIdentifiers.Error.message]
    }

    /// Get the retry button
    var retryButton: XCUIElement {
        app.buttons[AccessibilityIdentifiers.Error.retryButton]
    }

    /// Get the start over button
    var startOverButton: XCUIElement {
        app.buttons[AccessibilityIdentifiers.Error.startOverButton]
    }

    /// Get a rating badge by wine name
    func ratingBadge(for wineName: String) -> XCUIElement {
        app.otherElements[AccessibilityIdentifiers.Results.ratingBadge(wineName: wineName)]
    }

    // MARK: - Action Helpers

    /// Simulate selecting a photo from the library
    /// Note: In UI tests, we rely on mocks, so this taps the button and waits for results
    func selectPhotoAndWaitForResults(timeout: TimeInterval? = nil) {
        choosePhotoButton.tap()
        assertExists(resultsView, timeout: timeout)
    }

    /// Dismiss the detail sheet by swiping down
    func dismissDetailSheet() {
        wineDetailSheet.swipeDown()
    }
}
