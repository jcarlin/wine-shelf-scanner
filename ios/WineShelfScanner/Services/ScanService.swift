import UIKit

/// Protocol for scan services (allows mock/real swapping)
protocol ScanServiceProtocol {
    func scan(image: UIImage, debug: Bool, compressionQuality: CGFloat) async throws -> ScanResponse
}

extension ScanServiceProtocol {
    /// Default compression quality for backward compatibility
    func scan(image: UIImage, debug: Bool) async throws -> ScanResponse {
        try await scan(image: image, debug: debug, compressionQuality: 0.8)
    }
}

/// Errors from the scan service
enum ScanError: LocalizedError {
    case invalidImage
    case networkError(Error)
    case serverError(Int)
    case decodingError(Error)
    case timeout
    case unknown

    var errorDescription: String? {
        switch self {
        case .invalidImage:
            return "Could not process the image"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .serverError(let code):
            return "Server error: \(code)"
        case .decodingError:
            return "Invalid response from server"
        case .timeout:
            return "Request timed out"
        case .unknown:
            return "An unknown error occurred"
        }
    }
}

/// Real API client for scan endpoint (Phase 4)
class ScanAPIClient: ScanServiceProtocol {
    private let baseURL: URL
    private let session: URLSession
    private let attestManager: AppAttestManager?

    init(baseURL: URL, session: URLSession = .shared, attestManager: AppAttestManager? = nil) {
        self.baseURL = baseURL
        self.session = session
        self.attestManager = attestManager
    }

    func scan(image: UIImage, debug: Bool = false, compressionQuality: CGFloat = 0.8) async throws -> ScanResponse {
        guard let imageData = image.jpegData(compressionQuality: compressionQuality) else {
            throw ScanError.invalidImage
        }

        // Merge device attestation headers ([:] whenever attestation is
        // unavailable — never blocks or fails the scan)
        var attestHeaders: [String: String] = [:]
        if let attestManager = attestManager {
            attestHeaders = await attestManager.prepareHeaders()
        }

        do {
            return try await performScan(imageData: imageData, debug: debug, attestHeaders: attestHeaders)
        } catch ScanError.serverError(403) where !attestHeaders.isEmpty {
            // The server rejected our assertion (e.g. its device registry was
            // wiped by a redeploy). Attestation must never cost the user a
            // scan: clear the registered state so a later scan re-registers,
            // and retry this scan exactly once WITHOUT attest headers.
            attestManager?.clearRegistration()
            return try await performScan(imageData: imageData, debug: debug, attestHeaders: [:])
        }
    }

    private func performScan(imageData: Data, debug: Bool, attestHeaders: [String: String]) async throws -> ScanResponse {
        var urlComponents = URLComponents(url: baseURL.appendingPathComponent("scan"), resolvingAgainstBaseURL: true)!
        if debug {
            urlComponents.queryItems = [URLQueryItem(name: "debug", value: "true")]
        }
        let url = urlComponents.url!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = Config.requestTimeout

        for (key, value) in attestHeaders {
            request.setValue(value, forHTTPHeaderField: key)
        }

        // Create multipart form data
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"shelf.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        do {
            let (data, response) = try await session.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw ScanError.unknown
            }

            guard (200...299).contains(httpResponse.statusCode) else {
                throw ScanError.serverError(httpResponse.statusCode)
            }

            let decoder = JSONDecoder()
            return try decoder.decode(ScanResponse.self, from: data)
        } catch let error as ScanError {
            throw error
        } catch let error as DecodingError {
            throw ScanError.decodingError(error)
        } catch {
            throw ScanError.networkError(error)
        }
    }
}
