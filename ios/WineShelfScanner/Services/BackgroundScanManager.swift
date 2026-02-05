import UIKit

/// Manages background URLSession uploads for wine shelf scanning.
///
/// Uses a background URLSession so that scan uploads continue even when
/// the app is suspended or terminated. When the scan completes, results
/// are persisted and a local notification is posted.
///
/// ## Lifecycle
/// 1. `startScan(image:debug:)` — writes multipart body to a temp file,
///    persists a `PendingScan` record, starts a background upload task.
/// 2. If the app stays in foreground, delegate callbacks fire normally.
/// 3. If the app is suspended/terminated, iOS continues the upload and
///    relaunches the app in the background to deliver the response.
/// 4. `handleBackgroundSessionEvents(completionHandler:)` is called from
///    the AppDelegate to reconnect the background session.
/// 5. On completion, the result is cached, a notification is posted, and
///    `completedScan` is published for the UI.
final class BackgroundScanManager: NSObject, ObservableObject {
    static let shared = BackgroundScanManager()

    static let sessionIdentifier = "com.wineshelfscanner.background-scan"

    /// Published when a background scan completes. The ViewModel observes this.
    @Published var completedScan: CompletedBackgroundScan?

    /// Whether a background scan is currently in progress.
    @Published private(set) var isScanning: Bool = false

    /// Completion handler from the system for background session events.
    /// Must be called after all delegate events have been delivered.
    var systemCompletionHandler: (() -> Void)?

    // MARK: - Private State

    private var responseBuffers: [Int: Data] = [:]
    private var pendingScans: [Int: PendingScan] = [:]

    private lazy var backgroundSession: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: Self.sessionIdentifier)
        config.isDiscretionary = false
        config.sessionSendsLaunchEvents = true
        config.timeoutIntervalForResource = 120 // 2 minutes max for background
        return URLSession(configuration: config, delegate: self, delegateQueue: .main)
    }()

    // MARK: - Init

    private override init() {
        super.init()
        restorePendingScans()
        // Access backgroundSession to reconnect if there are pending tasks
        _ = backgroundSession
    }

    // MARK: - Public API

    /// Start a background scan upload.
    ///
    /// - Parameters:
    ///   - image: The wine shelf photo to scan.
    ///   - debug: Whether to request debug data from the API.
    /// - Throws: `ScanError.invalidImage` if JPEG conversion fails.
    func startScan(image: UIImage, debug: Bool) throws {
        guard let imageData = image.jpegData(compressionQuality: 0.8) else {
            throw ScanError.invalidImage
        }

        // Build multipart form body
        let boundary = UUID().uuidString
        let bodyData = buildMultipartBody(imageData: imageData, boundary: boundary)

        // Write body to temp file (required for background upload)
        let tempDir = FileManager.default.temporaryDirectory
        let bodyFileURL = tempDir.appendingPathComponent("scan_upload_\(UUID().uuidString).tmp")
        try bodyData.write(to: bodyFileURL)

        // Save image for results display later
        let imageFileURL = pendingScanDirectory.appendingPathComponent("\(UUID().uuidString).jpg")
        try imageData.write(to: imageFileURL)

        // Build request
        var urlComponents = URLComponents(
            url: Config.apiBaseURL.appendingPathComponent("scan"),
            resolvingAgainstBaseURL: true
        )!
        if debug {
            urlComponents.queryItems = [URLQueryItem(name: "debug", value: "true")]
        }

        var request = URLRequest(url: urlComponents.url!)
        request.httpMethod = "POST"
        request.setValue(
            "multipart/form-data; boundary=\(boundary)",
            forHTTPHeaderField: "Content-Type"
        )

        // Create background upload task
        let task = backgroundSession.uploadTask(with: request, fromFile: bodyFileURL)

        // Persist pending scan context
        let pendingScan = PendingScan(
            taskIdentifier: task.taskIdentifier,
            imageFilePath: imageFileURL.path,
            bodyFilePath: bodyFileURL.path,
            startedAt: Date()
        )
        pendingScans[task.taskIdentifier] = pendingScan
        savePendingScans()

        isScanning = true
        task.resume()
    }

    /// Check if there's a completed scan waiting to be shown.
    /// Called when the app returns to foreground.
    func checkForCompletedScan() {
        // completedScan is already published — ViewModel observes it
    }

    /// Clear the completed scan after the UI has consumed it.
    func clearCompletedScan() {
        completedScan = nil
    }

    /// Cancel any active background scan.
    func cancelActiveScan() {
        backgroundSession.getAliveTasks { dataTasks, uploadTasks, downloadTasks in
            for task in uploadTasks {
                task.cancel()
            }
        }
        cleanupAllPendingScans()
        isScanning = false
    }

    /// Called from AppDelegate when the system delivers background session events.
    func handleBackgroundSessionEvents(completionHandler: @escaping () -> Void) {
        systemCompletionHandler = completionHandler
        // Accessing backgroundSession reconnects the delegate
        _ = backgroundSession
    }
}

// MARK: - URLSessionDataDelegate

extension BackgroundScanManager: URLSessionDataDelegate {

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        // Accumulate response data
        var buffer = responseBuffers[dataTask.taskIdentifier] ?? Data()
        buffer.append(data)
        responseBuffers[dataTask.taskIdentifier] = buffer
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        let taskId = task.taskIdentifier

        defer {
            responseBuffers.removeValue(forKey: taskId)
            if let pending = pendingScans.removeValue(forKey: taskId) {
                // Clean up temp body file
                try? FileManager.default.removeItem(atPath: pending.bodyFilePath)
            }
            savePendingScans()

            if pendingScans.isEmpty {
                isScanning = false
            }
        }

        guard let pending = pendingScans[taskId] else { return }

        if let error = error {
            handleScanFailure(pending: pending, error: error)
            return
        }

        guard let responseData = responseBuffers[taskId],
              let httpResponse = task.response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            let statusCode = (task.response as? HTTPURLResponse)?.statusCode ?? -1
            handleScanFailure(
                pending: pending,
                error: ScanError.serverError(statusCode)
            )
            return
        }

        // Decode response
        do {
            let decoder = JSONDecoder()
            let scanResponse = try decoder.decode(ScanResponse.self, from: responseData)
            let image = UIImage(contentsOfFile: pending.imageFilePath)

            // Cache result for offline access
            if let image = image {
                ScanCacheService.shared.save(response: scanResponse, image: image)
            }

            // Save completed scan for the UI
            let completed = CompletedBackgroundScan(
                response: scanResponse,
                imageFilePath: pending.imageFilePath,
                completedAt: Date()
            )
            saveCompletedScan(completed)

            DispatchQueue.main.async { [weak self] in
                self?.completedScan = completed
            }

            // Notify user if app is in background
            if UIApplication.shared.applicationState != .active {
                let topWine = scanResponse.topRatedResults.first
                NotificationService.shared.notifyScanComplete(
                    wineCount: scanResponse.results.count,
                    bestWine: topWine?.wineName,
                    bestRating: topWine?.rating
                )
            }
        } catch {
            handleScanFailure(pending: pending, error: ScanError.decodingError(error))
        }
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        DispatchQueue.main.async { [weak self] in
            self?.systemCompletionHandler?()
            self?.systemCompletionHandler = nil
        }
    }
}

// MARK: - Private Helpers

private extension BackgroundScanManager {

    func handleScanFailure(pending: PendingScan, error: Error) {
        // Clean up saved image
        try? FileManager.default.removeItem(atPath: pending.imageFilePath)
        clearSavedCompletedScan()

        if UIApplication.shared.applicationState != .active {
            NotificationService.shared.notifyScanFailed()
        }

        DispatchQueue.main.async { [weak self] in
            // Signal failure via a nil completedScan — ViewModel handles error state
            self?.completedScan = nil
        }
    }

    func buildMultipartBody(imageData: Data, boundary: String) -> Data {
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append(
            "Content-Disposition: form-data; name=\"image\"; filename=\"shelf.jpg\"\r\n"
                .data(using: .utf8)!
        )
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        return body
    }

    // MARK: - Persistence

    var pendingScanDirectory: URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("background_scans", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    var pendingScansFileURL: URL {
        pendingScanDirectory.appendingPathComponent("pending_scans.json")
    }

    var completedScanFileURL: URL {
        pendingScanDirectory.appendingPathComponent("completed_scan.json")
    }

    func savePendingScans() {
        let entries = Array(pendingScans.values)
        if let data = try? JSONEncoder().encode(entries) {
            try? data.write(to: pendingScansFileURL)
        }
    }

    func restorePendingScans() {
        guard let data = try? Data(contentsOf: pendingScansFileURL),
              let entries = try? JSONDecoder().decode([PendingScan].self, from: data) else {
            // Check for a completed scan from a previous session
            restoreCompletedScan()
            return
        }

        for entry in entries {
            pendingScans[entry.taskIdentifier] = entry
        }
        if !entries.isEmpty {
            isScanning = true
        }

        // Also check for completed scan
        restoreCompletedScan()
    }

    func cleanupAllPendingScans() {
        for pending in pendingScans.values {
            try? FileManager.default.removeItem(atPath: pending.bodyFilePath)
            try? FileManager.default.removeItem(atPath: pending.imageFilePath)
        }
        pendingScans.removeAll()
        savePendingScans()
    }

    func saveCompletedScan(_ scan: CompletedBackgroundScan) {
        if let data = try? JSONEncoder().encode(scan) {
            try? data.write(to: completedScanFileURL)
        }
    }

    func restoreCompletedScan() {
        guard let data = try? Data(contentsOf: completedScanFileURL),
              let scan = try? JSONDecoder().decode(CompletedBackgroundScan.self, from: data) else {
            return
        }
        completedScan = scan
    }

    func clearSavedCompletedScan() {
        try? FileManager.default.removeItem(at: completedScanFileURL)
    }
}

// MARK: - URLSession convenience

private extension URLSession {
    func getAliveTasks(completion: @escaping ([URLSessionDataTask], [URLSessionUploadTask], [URLSessionDownloadTask]) -> Void) {
        getAllTasks { tasks in
            var dataTasks: [URLSessionDataTask] = []
            var uploadTasks: [URLSessionUploadTask] = []
            var downloadTasks: [URLSessionDownloadTask] = []
            for task in tasks {
                if let t = task as? URLSessionUploadTask { uploadTasks.append(t) }
                else if let t = task as? URLSessionDataTask { dataTasks.append(t) }
                else if let t = task as? URLSessionDownloadTask { downloadTasks.append(t) }
            }
            completion(dataTasks, uploadTasks, downloadTasks)
        }
    }
}

// MARK: - Supporting Types

/// Context for a scan that is currently uploading in the background.
struct PendingScan: Codable {
    let taskIdentifier: Int
    let imageFilePath: String
    let bodyFilePath: String
    let startedAt: Date
}

/// Result from a completed background scan, persisted to disk so it
/// survives app termination.
struct CompletedBackgroundScan: Codable {
    let response: ScanResponse
    let imageFilePath: String
    let completedAt: Date

    /// Load the original image from the persisted file path.
    var image: UIImage? {
        UIImage(contentsOfFile: imageFilePath)
    }

    /// Clean up the persisted image file.
    func cleanup() {
        try? FileManager.default.removeItem(atPath: imageFilePath)
    }
}
