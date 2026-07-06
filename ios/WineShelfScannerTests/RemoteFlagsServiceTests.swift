import XCTest
@testable import WineShelfScanner

final class RemoteFlagsServiceTests: XCTestCase {

    private let flagKey = "feature_subscription"
    private var service: RemoteFlagsService!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        FeatureFlags.shared.removeOverride(flagKey)
        service = RemoteFlagsService(
            baseURL: URL(string: "https://api.example.com")!,
            session: MockURLProtocol.mockSession()
        )
    }

    override func tearDown() {
        FeatureFlags.shared.removeOverride(flagKey)
        MockURLProtocol.reset()
        service = nil
        super.tearDown()
    }

    func testAppliesSubscriptionFlagFromServer() async {
        MockURLProtocol.setSuccessResponse(json: #"{"feature_subscription": true}"#)

        let applied = await service.refresh()

        XCTAssertTrue(applied)
        XCTAssertEqual(MockURLProtocol.lastRequest?.url?.path, "/config")
        XCTAssertTrue(FeatureFlags.shared.subscription)
    }

    func testDisablesFlagWhenServerSaysFalse() async {
        FeatureFlags.shared.setOverride(flagKey, value: true)
        MockURLProtocol.setSuccessResponse(json: #"{"feature_subscription": false}"#)

        let applied = await service.refresh()

        XCTAssertTrue(applied)
        XCTAssertFalse(FeatureFlags.shared.subscription)
    }

    func testKeepsPersistedOverrideOnServerError() async {
        // Previous launch enabled the flag; a failing /config must not undo it
        FeatureFlags.shared.setOverride(flagKey, value: true)
        MockURLProtocol.setErrorResponse(statusCode: 500)

        let applied = await service.refresh()

        XCTAssertFalse(applied)
        XCTAssertTrue(FeatureFlags.shared.subscription)
    }

    func testKeepsPersistedOverrideOnNetworkError() async {
        FeatureFlags.shared.setOverride(flagKey, value: true)
        MockURLProtocol.setNetworkError(URLError(.notConnectedToInternet))

        let applied = await service.refresh()

        XCTAssertFalse(applied)
        XCTAssertTrue(FeatureFlags.shared.subscription)
    }

    func testKeepsCompiledDefaultOnFailureWithNoOverride() async {
        MockURLProtocol.setErrorResponse(statusCode: 503)

        let applied = await service.refresh()

        XCTAssertFalse(applied)
        // Compiled default for feature_subscription is false
        XCTAssertFalse(FeatureFlags.shared.subscription)
    }

    func testMalformedResponseKeepsExistingValue() async {
        FeatureFlags.shared.setOverride(flagKey, value: true)
        MockURLProtocol.setSuccessResponse(json: "{ not json }")

        let applied = await service.refresh()

        XCTAssertFalse(applied)
        XCTAssertTrue(FeatureFlags.shared.subscription)
    }
}
