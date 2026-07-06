import XCTest
@testable import WineShelfScanner

final class WarmupServiceTests: XCTestCase {

    private var service: WarmupService!

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        service = WarmupService(
            baseURL: URL(string: "https://api.example.com")!,
            session: MockURLProtocol.mockSession()
        )
    }

    override func tearDown() {
        MockURLProtocol.reset()
        service = nil
        super.tearDown()
    }

    func testPingHitsHealthEndpoint() async {
        MockURLProtocol.setSuccessResponse(json: #"{"status":"ok"}"#)

        let result = await service.ping()

        XCTAssertTrue(result)
        XCTAssertEqual(MockURLProtocol.lastRequest?.url?.path, "/health")
        XCTAssertEqual(MockURLProtocol.lastRequest?.httpMethod, "GET")
    }

    func testPingReturnsFalseOnServerError() async {
        MockURLProtocol.setErrorResponse(statusCode: 503)

        let result = await service.ping()

        XCTAssertFalse(result)
    }

    func testPingReturnsFalseOnNetworkError() async {
        MockURLProtocol.setNetworkError(URLError(.notConnectedToInternet))

        let result = await service.ping()

        XCTAssertFalse(result)
    }
}
