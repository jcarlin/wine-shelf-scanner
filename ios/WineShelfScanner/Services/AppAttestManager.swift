import Foundation
import CryptoKit
import DeviceCheck

/// Abstraction over DCAppAttestService so tests can mock attestation.
protocol AttestServiceProtocol {
    var isSupported: Bool { get }
    func generateKey() async throws -> String
    func attestKey(_ keyId: String, clientDataHash: Data) async throws -> Data
    func generateAssertion(_ keyId: String, clientDataHash: Data) async throws -> Data
}

extension DCAppAttestService: AttestServiceProtocol {}

/// Manages the App Attest key lifecycle and produces per-scan assertion headers.
///
/// Lifecycle: generate a key once (key id persisted), attest it against a
/// server challenge via POST /device/register, then sign a fresh single-use
/// challenge per scan with `generateAssertion`.
///
/// Attestation must NEVER block or fail a scan: any unavailability (simulator,
/// server 503 = not configured, network/attest errors) degrades to empty
/// headers — the server currently admits unattested scans in "log" mode.
final class AppAttestManager {
    static let shared = AppAttestManager()

    static let keyIdDefaultsKey = "app_attest_key_id"
    static let registeredDefaultsKey = "app_attest_registered"

    private let service: AttestServiceProtocol
    private let baseURL: URL
    private let session: URLSession
    private let defaults: UserDefaults

    init(
        service: AttestServiceProtocol = DCAppAttestService.shared,
        baseURL: URL = Config.apiBaseURL,
        session: URLSession = .shared,
        defaults: UserDefaults = .standard
    ) {
        self.service = service
        self.baseURL = baseURL
        self.session = session
        self.defaults = defaults
    }

    /// The three X-Attest-* headers for a scan, or [:] if anything is
    /// unavailable or fails.
    func prepareHeaders() async -> [String: String] {
        guard service.isSupported else { return [:] }
        do {
            let keyId = try await ensureRegisteredKey()
            let challenge = try await fetchChallenge()
            guard let challengeData = Data(base64Encoded: challenge) else { return [:] }
            let clientDataHash = Data(SHA256.hash(data: challengeData))
            let assertion = try await service.generateAssertion(keyId, clientDataHash: clientDataHash)
            return [
                "X-Attest-Key-Id": keyId,
                "X-Attest-Assertion": assertion.base64EncodedString(),
                "X-Attest-Challenge": challenge,
            ]
        } catch {
            #if DEBUG
            print("🍷 App Attest unavailable, sending unattested scan: \(error)")
            #endif
            return [:]
        }
    }

    /// Clear the registered state (e.g. after the server rejects an
    /// assertion with 403) so the next scan re-registers.
    func clearRegistration() {
        defaults.removeObject(forKey: Self.registeredDefaultsKey)
    }

    // MARK: - Private

    private enum AttestError: Error {
        case registrationRejected(statusCode: Int)
        case badChallengeResponse
    }

    /// Returns the device key id, generating and registering it if needed.
    private func ensureRegisteredKey() async throws -> String {
        let keyId: String
        if let stored = defaults.string(forKey: Self.keyIdDefaultsKey) {
            keyId = stored
        } else {
            keyId = try await service.generateKey()
            defaults.set(keyId, forKey: Self.keyIdDefaultsKey)
        }

        if defaults.bool(forKey: Self.registeredDefaultsKey) {
            return keyId
        }

        try await register(keyId: keyId)
        defaults.set(true, forKey: Self.registeredDefaultsKey)
        return keyId
    }

    /// One-time attestation: attest the key over a server challenge and
    /// POST it to /device/register. 503 means the server has no
    /// APPLE_TEAM_ID configured yet — throw so this scan goes unattested
    /// and registration is retried on a later scan.
    private func register(keyId: String) async throws {
        let challenge = try await fetchChallenge()
        guard let challengeData = Data(base64Encoded: challenge) else {
            throw AttestError.badChallengeResponse
        }
        let clientDataHash = Data(SHA256.hash(data: challengeData))
        let attestation = try await service.attestKey(keyId, clientDataHash: clientDataHash)

        var request = URLRequest(url: baseURL.appendingPathComponent("device/register"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "key_id": keyId,
            "attestation": attestation.base64EncodedString(),
            "challenge": challenge,
        ])

        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw AttestError.registrationRejected(statusCode: code)
        }
    }

    /// POST /device/challenge → single-use base64 challenge.
    private func fetchChallenge() async throws -> String {
        var request = URLRequest(url: baseURL.appendingPathComponent("device/challenge"))
        request.httpMethod = "POST"

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200...299).contains(http.statusCode) else {
            throw AttestError.badChallengeResponse
        }

        struct ChallengeResponse: Decodable {
            let challenge: String
        }
        return try JSONDecoder().decode(ChallengeResponse.self, from: data).challenge
    }
}
