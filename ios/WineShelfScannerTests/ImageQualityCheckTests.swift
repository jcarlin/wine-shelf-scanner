import XCTest
@testable import WineShelfScanner

final class ImageQualityCheckTests: XCTestCase {

    // MARK: - Pixel Threshold

    func testBelowThreshold() {
        // 1000 × 1000 = 1 MP — below the ~2 MP recommendation
        XCTAssertTrue(ImageQualityCheck.isBelowRecommendedResolution(pixelWidth: 1000, pixelHeight: 1000))
    }

    func testAboveThreshold() {
        // 4032 × 3024 = 12.2 MP — typical iPhone photo
        XCTAssertFalse(ImageQualityCheck.isBelowRecommendedResolution(pixelWidth: 4032, pixelHeight: 3024))
    }

    func testExactlyAtThresholdIsAcceptable() {
        // 2,000,000 px exactly is not below the threshold
        XCTAssertFalse(ImageQualityCheck.isBelowRecommendedResolution(pixelWidth: 2000, pixelHeight: 1000))
    }

    func testJustBelowThreshold() {
        // 1,999,000 px is below
        XCTAssertTrue(ImageQualityCheck.isBelowRecommendedResolution(pixelWidth: 1999, pixelHeight: 1000))
    }

    func testAspectRatioDoesNotMatter() {
        // Same pixel count, extreme aspect ratio
        XCTAssertFalse(ImageQualityCheck.isBelowRecommendedResolution(pixelWidth: 8000, pixelHeight: 250))
        XCTAssertTrue(ImageQualityCheck.isBelowRecommendedResolution(pixelWidth: 7996, pixelHeight: 250))
    }

    // MARK: - UIImage Variant

    func testUIImageBelowThreshold() {
        let image = TestFixtures.testImage(size: CGSize(width: 400, height: 600))
        XCTAssertTrue(ImageQualityCheck.isBelowRecommendedResolution(image))
    }

    func testUIImageAboveThreshold() {
        let image = TestFixtures.testImage(size: CGSize(width: 2000, height: 1500))
        XCTAssertFalse(ImageQualityCheck.isBelowRecommendedResolution(image))
    }

    func testUIImageAccountsForScale() {
        // 800 × 900 points at 2x scale = 1600 × 1800 px = 2.88 MP → acceptable
        let size = CGSize(width: 800, height: 900)
        UIGraphicsBeginImageContextWithOptions(size, false, 2.0)
        UIColor.gray.setFill()
        UIRectFill(CGRect(origin: .zero, size: size))
        let image = UIGraphicsGetImageFromCurrentImageContext()!
        UIGraphicsEndImageContext()

        XCTAssertEqual(image.scale, 2.0)
        XCTAssertFalse(ImageQualityCheck.isBelowRecommendedResolution(image))
    }
}
