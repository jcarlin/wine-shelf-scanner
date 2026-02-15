import UIKit

/// Server health status for cold start detection
enum ServerHealthStatus {
    case healthy
    case warmingUp(retryAfter: Int)
    case unavailable(message: String)
}

/// Protocol for scan services (allows mock/real swapping)
protocol ScanServiceProtocol {
    func scan(image: UIImage, debug: Bool, compressionQuality: CGFloat) async throws -> ScanResponse
    func checkHealth() async -> ServerHealthStatus
    func fetchWineReviews(wineId: Int, limit: Int, textOnly: Bool) async -> WineReviewsResponse?
}

extension ScanServiceProtocol {
    /// Default compression quality for backward compatibility
    func scan(image: UIImage, debug: Bool) async throws -> ScanResponse {
        try await scan(image: image, debug: debug, compressionQuality: 0.8)
    }

    /// Default parameters for review fetching
    func fetchWineReviews(wineId: Int) async -> WineReviewsResponse? {
        await fetchWineReviews(wineId: wineId, limit: 5, textOnly: true)
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

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func scan(image: UIImage, debug: Bool = false, compressionQuality: CGFloat = 0.8) async throws -> ScanResponse {
        guard let imageData = image.jpegData(compressionQuality: compressionQuality) else {
            throw ScanError.invalidImage
        }

        var urlComponents = URLComponents(url: baseURL.appendingPathComponent("scan"), resolvingAgainstBaseURL: true)!
        if debug {
            urlComponents.queryItems = [URLQueryItem(name: "debug", value: "true")]
        }
        let url = urlComponents.url!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = Config.requestTimeout

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

    // MARK: - Health Check

    func checkHealth() async -> ServerHealthStatus {
        let url = baseURL.appendingPathComponent("health")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        do {
            let (_, response) = try await session.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                return .unavailable(message: "Invalid response")
            }

            if httpResponse.statusCode == 200 {
                return .healthy
            }

            if httpResponse.statusCode == 503 {
                let retryAfter = httpResponse.value(forHTTPHeaderField: "Retry-After")
                    .flatMap { Int($0) } ?? 10
                return .warmingUp(retryAfter: retryAfter)
            }

            return .unavailable(message: "Server returned \(httpResponse.statusCode)")
        } catch {
            // Network error likely means server is cold starting
            return .warmingUp(retryAfter: 5)
        }
    }

    // MARK: - Wine Reviews

    func fetchWineReviews(wineId: Int, limit: Int = 5, textOnly: Bool = true) async -> WineReviewsResponse? {
        var urlComponents = URLComponents(url: baseURL.appendingPathComponent("wines/\(wineId)/reviews"), resolvingAgainstBaseURL: true)!
        urlComponents.queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "text_only", value: String(textOnly))
        ]

        guard let url = urlComponents.url else { return nil }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.timeoutInterval = 10
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        do {
            let (data, response) = try await session.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                return nil
            }

            return try JSONDecoder().decode(WineReviewsResponse.self, from: data)
        } catch {
            return nil
        }
    }
}
