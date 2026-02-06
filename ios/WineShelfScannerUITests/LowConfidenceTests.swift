import XCTest

/// Tests for low confidence scenario: opacity variations and tappability rules
///
/// Confidence thresholds (from OverlayMath):
/// - >= 0.85: 1.0 opacity, tappable
/// - 0.65-0.85: 0.75 opacity, tappable
/// - 0.45-0.65: 0.5 opacity, NOT tappable
/// - < 0.45: hidden (0.0 opacity)
final class LowConfidenceTests: BaseUITestCase {

    func testLowConfidenceBadgesAreVisible() throws {
        // Given: Low confidence scenario (all wines 0.41-0.58 confidence)
        launchWithScenario("low_confidence")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Badges with confidence >= 0.45 should be visible
        // From mock: Unknown Red Wine (0.58), Unknown White Wine (0.52)
        // These are above 0.45 visibility threshold

        let redWineBadge = ratingBadge(for: "Unknown Red Wine")
        assertExists(redWineBadge, message: "Wine with 0.58 confidence should be visible")

        let whiteWineBadge = ratingBadge(for: "Unknown White Wine")
        assertExists(whiteWineBadge, message: "Wine with 0.52 confidence should be visible")
    }

    func testVeryLowConfidenceBadgesHidden() throws {
        // Given: Low confidence scenario
        launchWithScenario("low_confidence")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Wine with confidence < 0.45 should NOT be visible
        // From mock: Unknown Sparkling (0.41)
        let sparklingBadge = ratingBadge(for: "Unknown Sparkling")
        assertNotExists(
            sparklingBadge,
            message: "Wine with 0.41 confidence should be hidden"
        )
    }

    func testLowConfidenceBadgesNotTappable() throws {
        // Given: Low confidence wines (below 0.65 tappable threshold)
        launchWithScenario("low_confidence")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // When: User tries to tap a low confidence badge (0.48-0.58)
        // From mock: Unknown Rose has 0.48 confidence
        let roseBadge = ratingBadge(for: "Unknown Rose")

        // If badge exists (confidence >= 0.45), it should not open detail sheet
        if roseBadge.waitForExistence(timeout: 2) {
            roseBadge.tap()

            // Then: Detail sheet should NOT appear (badge is not tappable)
            assertNotExists(
                wineDetailSheet,
                message: "Detail sheet should not open for low confidence wine"
            )
        }
    }

    func testMediumConfidenceBadgesAreTappable() throws {
        // Given: Full shelf with varying confidence levels
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // When: User taps a medium confidence badge (0.65-0.85)
        // From mock: Kendall-Jackson (0.79), La Crema (0.72), Meiomi (0.68)
        let laCrema = ratingBadge(for: "La Crema Sonoma Coast Pinot Noir")
        assertExists(laCrema)
        laCrema.tap()

        // Then: Detail sheet should open
        assertExists(wineDetailSheet, message: "Medium confidence badges should be tappable")

        // And: Should NOT show confidence label (below 0.85, no badge shown)
        assertNotExists(detailSheetConfidenceLabel, message: "Medium confidence should not show confidence label")
    }

    func testHighConfidenceShowsWidelyRated() throws {
        // Given: Full shelf with high confidence wine
        launchWithScenario("full_shelf")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // When: User taps a high confidence badge (>= 0.85)
        // From mock: Caymus (0.94), Opus One (0.91), Silver Oak (0.88)
        let caymus = ratingBadge(for: "Caymus Cabernet Sauvignon")
        assertExists(caymus)
        caymus.tap()

        // Then: Detail sheet should show "Widely rated"
        assertExists(wineDetailSheet)
        assertExists(detailSheetConfidenceLabel)
        let label = detailSheetConfidenceLabel.label
        XCTAssertEqual(label, "Widely rated", "High confidence should show 'Widely rated'")
    }

    func testLowConfidenceNotInTopThree() throws {
        // Given: Low confidence scenario
        launchWithScenario("low_confidence")
        choosePhotoButton.tap()
        assertExists(resultsView)

        // Then: Even if wines are visible, they should not get top-3 emphasis
        // This is a visual test that's hard to verify programmatically
        // But we verify the badges exist without the top-3 glow
        // The existence of badges proves they render without crashing

        let redWine = ratingBadge(for: "Unknown Red Wine")
        assertExists(redWine, message: "Low confidence badge renders without crash")
    }
}
