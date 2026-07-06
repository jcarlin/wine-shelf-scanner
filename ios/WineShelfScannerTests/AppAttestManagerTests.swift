import XCTest
import CryptoKit
@testable import WineShelfScanner

/// Mock DCAppAttestService replacement.
private final class MockAttestService: AttestServiceProtocol {
    var isSupported = true
    var keyIdToReturn = "mock-key-id-base64"
    var errorToThrow: Error?

    var generateKeyCallCount = 0
    var attestKeyCallCount = 0
    var generateAssertionCallCount = 0
    var lastAttestClientDataHash: Data?
    var lastAssertionClientDataHash: Data?

    func generateKey() async throws -> String {
        generateKeyCallCount += 1
        if let error = errorToThrow { throw error }
        return keyIdToReturn
    }

    func attestKey(_ keyId: String, clientDataHash: Data) async throws -> Data {
        attestKeyCallCount += 1
        lastAttestClientDataHash = clientDataHash
        if let error = errorToThrow { throw error }
        return Data("mock-attestation".utf8)
    }

    func generateAssertion(_ keyId: String, clientDataHash: Data) async throws -> Data {
        generateAssertionCallCount += 1
        lastAssertionClientDataHash = clientDataHash
        if let error = errorToThrow { throw error }
        return Data("mock-assertion".utf8)
    }
}

/// Note: real-device attestation (DCAppAttestService against Apple's servers)
/// cannot run in CI/simulator — it is a human verification gate. These tests
/// cover the state machine with a mocked attest service.
final class AppAttestManagerTests: XCTestCase {

    private let suiteName = "AppAttestManagerTests"
    private var defaults: UserDefaults!
    private var attestService: MockAttestService!
    private var manager: AppAttestManager!

    /// The single-use challenge the mock server hands out (base64 of raw bytes)
    private let challenge = Data("challenge-bytes-1".utf8).base64EncodedString()

    override func setUp() {
        super.setUp()
        MockURLProtocol.reset()
        defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        attestService = MockAttestService()
        manager = AppAttestManager(
            service: attestService,
            baseURL: URL(string: "https://api.example.com")!,
            session: MockURLProtocol.mockSession(),
            defaults: defaults
        )
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        MockURLProtocol.reset()
        manager = nil
        attestService = nil
        super.tearDown()
    }

    /// Route /device/challenge, /device/register and /scan like the backend.
    private func installServerHandler(registerStatus: Int = 204, scanStatus: Int = 200) {
        let challenge = self.challenge
        MockURLProtocol.requestHandler = { request in
            let path = request.url!.path
            switch path {
            case "/device/challenge":
                let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
                return (response, Data(#"{"challenge": "\#(challenge)"}"#.utf8))
            case "/device/register":
                let response = HTTPURLResponse(url: request.url!, statusCode: registerStatus, httpVersion: nil, headerFields: nil)!
                return (response, Data())
            case "/scan":
                let response = HTTPURLResponse(url: request.url!, statusCode: scanStatus, httpVersion: nil, headerFields: nil)!
                return (response, Data(#"{"image_id":"t","results":[],"fallback_list":[]}"#.utf8))
            default:
                let response = HTTPURLResponse(url: request.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!
                return (response, Data())
            }
        }
    }

    private func requests(to path: String) -> [URLRequest] {
        MockURLProtocol.capturedRequests.filter { $0.url?.path == path }
    }

    // MARK: - Graceful Degradation

    func testUnsupportedDeviceReturnsEmptyHeaders() async {
        attestService.isSupported = false
        installServerHandler()

        let headers = await manager.prepareHeaders()

        XCTAssertEqual(headers, [:])
        XCTAssertTrue(MockURLProtocol.capturedRequests.isEmpty, "No network calls when unsupported")
        XCTAssertEqual(attestService.generateKeyCallCount, 0)
    }

    func testServerNotConfigured503ReturnsEmptyAndRetriesLater() async {
        installServerHandler(registerStatus: 503)

        let headers = await manager.prepareHeaders()

        XCTAssertEqual(headers, [:])
        XCTAssertFalse(defaults.bool(forKey: AppAttestManager.registeredDefaultsKey))

        // Next scan tries to register again
        installServerHandler(registerStatus: 204)
        let retryHeaders = await manager.prepareHeaders()

        XCTAssertEqual(attestService.attestKeyCallCount, 2)
        XCTAssertFalse(retryHeaders.isEmpty)
    }

    func testAttestServiceErrorReturnsEmptyHeaders() async {
        attestService.errorToThrow = NSError(domain: "DCError", code: 2)
        installServerHandler()

        let headers = await manager.prepareHeaders()

        XCTAssertEqual(headers, [:])
    }

    func testNetworkErrorReturnsEmptyHeaders() async {
        MockURLProtocol.setNetworkError(URLError(.notConnectedToInternet))

        let headers = await manager.prepareHeaders()

        XCTAssertEqual(headers, [:])
    }

    // MARK: - Happy Path

    func testFirstScanRegistersKeyAndBuildsHeaders() async {
        installServerHandler()

        let headers = await manager.prepareHeaders()

        // Key generated once and persisted
        XCTAssertEqual(attestService.generateKeyCallCount, 1)
        XCTAssertEqual(defaults.string(forKey: AppAttestManager.keyIdDefaultsKey), "mock-key-id-base64")
        XCTAssertTrue(defaults.bool(forKey: AppAttestManager.registeredDefaultsKey))

        // Registration POSTed once
        XCTAssertEqual(attestService.attestKeyCallCount, 1)
        XCTAssertEqual(requests(to: "/device/register").count, 1)

        // Two challenges: one for attestation, one fresh for the assertion
        XCTAssertEqual(requests(to: "/device/challenge").count, 2)

        // Headers
        XCTAssertEqual(headers["X-Attest-Key-Id"], "mock-key-id-base64")
        XCTAssertEqual(headers["X-Attest-Assertion"], Data("mock-assertion".utf8).base64EncodedString())
        XCTAssertEqual(headers["X-Attest-Challenge"], challenge)

        // Assertion signed over SHA256 of the raw challenge bytes
        let expectedHash = Data(SHA256.hash(data: Data(base64Encoded: challenge)!))
        XCTAssertEqual(attestService.lastAssertionClientDataHash, expectedHash)
        XCTAssertEqual(attestService.lastAttestClientDataHash, expectedHash)
    }

    func testSubsequentScansSkipRegistration() async {
        installServerHandler()

        _ = await manager.prepareHeaders()
        let secondHeaders = await manager.prepareHeaders()

        // Still only one key generation and one registration
        XCTAssertEqual(attestService.generateKeyCallCount, 1)
        XCTAssertEqual(attestService.attestKeyCallCount, 1)
        XCTAssertEqual(requests(to: "/device/register").count, 1)

        // But a fresh challenge and assertion per scan
        XCTAssertEqual(attestService.generateAssertionCallCount, 2)
        XCTAssertEqual(requests(to: "/device/challenge").count, 3)
        XCTAssertFalse(secondHeaders.isEmpty)
    }

    func testClearRegistrationForcesReRegister() async {
        installServerHandler()
        _ = await manager.prepareHeaders()
        XCTAssertEqual(attestService.attestKeyCallCount, 1)

        // Server rejected an assertion (403) → client clears registered state
        manager.clearRegistration()

        _ = await manager.prepareHeaders()

        // Re-registered with the SAME key (no new generateKey)
        XCTAssertEqual(attestService.generateKeyCallCount, 1)
        XCTAssertEqual(attestService.attestKeyCallCount, 2)
        XCTAssertEqual(requests(to: "/device/register").count, 2)
    }

    func testRegisterRequestBodyContainsBase64Fields() async throws {
        installServerHandler()

        _ = await manager.prepareHeaders()

        let registerRequest = try XCTUnwrap(requests(to: "/device/register").first)
        let body = try XCTUnwrap(Self.drainBody(of: registerRequest))
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: String])

        XCTAssertEqual(json["key_id"], "mock-key-id-base64")
        XCTAssertEqual(json["attestation"], Data("mock-attestation".utf8).base64EncodedString())
        XCTAssertEqual(json["challenge"], challenge)
        XCTAssertEqual(registerRequest.value(forHTTPHeaderField: "Content-Type"), "application/json")
    }

    // MARK: - ScanAPIClient Integration

    func testScanRequestCarriesAttestHeaders() async throws {
        installServerHandler()
        let client = ScanAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            session: MockURLProtocol.mockSession(),
            attestManager: manager
        )

        _ = try await client.scan(image: TestFixtures.testImage, debug: false)

        let scanRequest = try XCTUnwrap(requests(to: "/scan").first)
        XCTAssertEqual(scanRequest.value(forHTTPHeaderField: "X-Attest-Key-Id"), "mock-key-id-base64")
        XCTAssertEqual(scanRequest.value(forHTTPHeaderField: "X-Attest-Assertion"), Data("mock-assertion".utf8).base64EncodedString())
        XCTAssertEqual(scanRequest.value(forHTTPHeaderField: "X-Attest-Challenge"), challenge)
    }

    func testScanWithoutAttestManagerSendsNoAttestHeaders() async throws {
        installServerHandler()
        let client = ScanAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            session: MockURLProtocol.mockSession()
        )

        _ = try await client.scan(image: TestFixtures.testImage, debug: false)

        let scanRequest = try XCTUnwrap(requests(to: "/scan").first)
        XCTAssertNil(scanRequest.value(forHTTPHeaderField: "X-Attest-Key-Id"))
    }

    func testScan403ClearsRegistrationSoNextScanReRegisters() async {
        installServerHandler(scanStatus: 403)
        let client = ScanAPIClient(
            baseURL: URL(string: "https://api.example.com")!,
            session: MockURLProtocol.mockSession(),
            attestManager: manager
        )

        // First scan registers, sends attested request, server rejects with 403
        do {
            _ = try await client.scan(image: TestFixtures.testImage, debug: false)
            XCTFail("Expected serverError(403)")
        } catch {
            guard case ScanError.serverError(403) = error else {
                return XCTFail("Expected serverError(403), got \(error)")
            }
        }

        // Registered state cleared → the next scan re-registers
        XCTAssertFalse(defaults.bool(forKey: AppAttestManager.registeredDefaultsKey))

        installServerHandler(scanStatus: 200)
        _ = try? await client.scan(image: TestFixtures.testImage, debug: false)
        XCTAssertEqual(attestService.attestKeyCallCount, 2)
    }

    // MARK: - Helpers

    /// URLSession moves httpBody into httpBodyStream before URLProtocol sees it.
    private static func drainBody(of request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let count = stream.read(buffer, maxLength: bufferSize)
            if count <= 0 { break }
            data.append(buffer, count: count)
        }
        return data
    }
}
