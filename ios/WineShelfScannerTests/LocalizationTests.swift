import XCTest

/// Verifies Localizable.strings is actually bundled into the app,
/// i.e. NSLocalizedString does not fall back to returning raw keys.
final class LocalizationTests: XCTestCase {

    func testEnglishLocalizableStringsIsBundled() {
        let path = Bundle.main.path(forResource: "Localizable", ofType: "strings", inDirectory: nil, forLocalization: "en")
        XCTAssertNotNil(path, "en.lproj/Localizable.strings missing from app bundle")
    }

    func testIdleScanShelfKeyIsLocalized() {
        let value = NSLocalizedString("idle.scanShelf", comment: "")
        XCTAssertNotEqual(value, "idle.scanShelf", "NSLocalizedString returned the raw key — Localizable.strings not wired into the app target")
    }
}
