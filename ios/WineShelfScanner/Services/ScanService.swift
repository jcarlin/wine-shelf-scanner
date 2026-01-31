import UIKit

/// Protocol for scan services (allows mock/real swapping)
protocol ScanServiceProtocol {
    func scan(image: UIImage) async throws -> ScanResponse
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

    func scan(image: UIImage) async throws -> ScanResponse {
        guard let imageData = image.jpegData(compressionQuality: 0.8) else {
            throw ScanError.invalidImage
        }

        let url = baseURL.appendingPathComponent("scan")
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
}
