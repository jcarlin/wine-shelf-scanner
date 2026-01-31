import XCTest
import CoreGraphics
@testable import WineShelfScanner

final class OverlayMathTests: XCTestCase {

    // MARK: - Anchor Point Tests

    func testAnchorPointCalculation() {
        let bbox = CGRect(x: 0.25, y: 0.40, width: 0.10, height: 0.30)
        let containerSize = CGSize(width: 400, height: 600)

        let anchor = OverlayMath.anchorPoint(bbox: bbox, geo: containerSize)

        // Expected: x = (0.25 + 0.10/2) * 400 = 0.30 * 400 = 120
        // Expected: y = (0.40 + 0.30 * 0.25) * 600 = 0.475 * 600 = 285
        XCTAssertEqual(anchor.x, 120, accuracy: 0.001)
        XCTAssertEqual(anchor.y, 285, accuracy: 0.001)
    }

    func testAnchorPointWithBoundingBoxModel() {
        let bbox = BoundingBox(x: 0.25, y: 0.40, width: 0.10, height: 0.30)
        let containerSize = CGSize(width: 400, height: 600)

        let anchor = OverlayMath.anchorPoint(bbox: bbox, geo: containerSize)

        XCTAssertEqual(anchor.x, 120, accuracy: 0.001)
        XCTAssertEqual(anchor.y, 285, accuracy: 0.001)
    }

    // MARK: - Opacity Tests

    func testOpacityHighConfidence() {
        XCTAssertEqual(OverlayMath.opacity(confidence: 1.0), 1.0)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.90), 1.0)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.85), 1.0)
    }

    func testOpacityMediumConfidence() {
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.84), 0.75)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.75), 0.75)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.65), 0.75)
    }

    func testOpacityLowConfidence() {
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.64), 0.5)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.55), 0.5)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.45), 0.5)
    }

    func testOpacityHidden() {
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.44), 0.0)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.30), 0.0)
        XCTAssertEqual(OverlayMath.opacity(confidence: 0.0), 0.0)
    }

    // MARK: - Visibility Tests

    func testIsVisible() {
        XCTAssertTrue(OverlayMath.isVisible(confidence: 0.90))
        XCTAssertTrue(OverlayMath.isVisible(confidence: 0.50))
        XCTAssertTrue(OverlayMath.isVisible(confidence: 0.45))
        XCTAssertFalse(OverlayMath.isVisible(confidence: 0.44))
        XCTAssertFalse(OverlayMath.isVisible(confidence: 0.30))
    }

    func testIsTappable() {
        XCTAssertTrue(OverlayMath.isTappable(confidence: 0.90))
        XCTAssertTrue(OverlayMath.isTappable(confidence: 0.65))
        XCTAssertFalse(OverlayMath.isTappable(confidence: 0.64))
        XCTAssertFalse(OverlayMath.isTappable(confidence: 0.50))
    }

    // MARK: - Badge Size Tests

    func testBadgeSizeNormal() {
        let size = OverlayMath.badgeSize(isTopThree: false)
        XCTAssertEqual(size, OverlayMath.baseBadgeSize)
        XCTAssertEqual(size.width, 44)
        XCTAssertEqual(size.height, 24)
    }

    func testBadgeSizeTopThree() {
        let size = OverlayMath.badgeSize(isTopThree: true)
        XCTAssertEqual(size, OverlayMath.topThreeBadgeSize)
        XCTAssertEqual(size.width, 52)
        XCTAssertEqual(size.height, 28)
    }

    // MARK: - Collision Avoidance Tests

    func testAdjustedAnchorPointClampsToLeftBound() {
        let point = CGPoint(x: 10, y: 100)
        let bbox = CGRect(x: 0, y: 0.2, width: 0.1, height: 0.3)
        let containerSize = CGSize(width: 400, height: 600)
        let badgeSize = CGSize(width: 44, height: 24)

        let adjusted = OverlayMath.adjustedAnchorPoint(point, bbox: bbox, geo: containerSize, badgeSize: badgeSize)

        // Should be clamped to minimum x (badgeSize.width/2 + padding = 26)
        XCTAssertGreaterThanOrEqual(adjusted.x, badgeSize.width / 2 + 4)
    }

    func testAdjustedAnchorPointClampsToRightBound() {
        let point = CGPoint(x: 395, y: 100)
        let bbox = CGRect(x: 0.9, y: 0.2, width: 0.1, height: 0.3)
        let containerSize = CGSize(width: 400, height: 600)
        let badgeSize = CGSize(width: 44, height: 24)

        let adjusted = OverlayMath.adjustedAnchorPoint(point, bbox: bbox, geo: containerSize, badgeSize: badgeSize)

        // Should be clamped to maximum x (containerWidth - badgeWidth/2 - padding = 374)
        XCTAssertLessThanOrEqual(adjusted.x, containerSize.width - badgeSize.width / 2 - 4)
    }

    func testAdjustedAnchorPointPartialBottle() {
        // Partial bottle (height < 0.15)
        let point = CGPoint(x: 200, y: 300)
        let bbox = CGRect(x: 0.4, y: 0.5, width: 0.1, height: 0.10) // Small height
        let containerSize = CGSize(width: 400, height: 600)
        let badgeSize = CGSize(width: 44, height: 24)

        let adjusted = OverlayMath.adjustedAnchorPoint(point, bbox: bbox, geo: containerSize, badgeSize: badgeSize)

        // Should anchor higher for partial bottles
        XCTAssertLessThan(adjusted.y, point.y)
    }
}
