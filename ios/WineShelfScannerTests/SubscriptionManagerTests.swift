import XCTest
import StoreKitTest
@testable import WineShelfScanner

/// Verifies the StoreKit configuration file (WineShelfScanner.storekit)
/// exposes both subscription products to SubscriptionManager.
@MainActor
final class SubscriptionManagerTests: XCTestCase {

    private var session: SKTestSession!

    override func setUp() async throws {
        try await super.setUp()
        session = try SKTestSession(configurationFileNamed: "WineShelfScanner")
        session.disableDialogs = true
        session.clearTransactions()
    }

    override func tearDown() async throws {
        session = nil
        try await super.tearDown()
    }

    func testLoadsBothSubscriptionProducts() async {
        let manager = SubscriptionManager()

        await manager.loadProducts()

        XCTAssertEqual(manager.products.count, 2)
        XCTAssertNotNil(manager.monthlyProduct, "com.wineshelfscanner.monthly should load")
        XCTAssertNotNil(manager.annualProduct, "com.wineshelfscanner.annual should load")
        XCTAssertEqual(manager.monthlyProduct?.displayName, "Monthly")
        XCTAssertEqual(manager.annualProduct?.displayName, "Annual")
        // Sorted by price: monthly ($4.99) before annual ($29.99)
        XCTAssertEqual(manager.products.first?.id, SubscriptionManager.monthlyProductID)
    }
}
