import UIKit
import ImageIO

/// Caches recent scan results for offline access.
///
/// Stores up to `maxEntries` scan responses with their images.
/// When offline or on poor connectivity, users can review recent scans.
struct ScanCacheService {
    static let shared = ScanCacheService()

    private let defaults = UserDefaults.standard
    private let cacheKey = "scan_cache_entries"
    private let maxEntries = 10

    struct CachedScan: Codable, Identifiable {
        let response: ScanResponse
        let timestamp: Date
        let imageFileName: String

        var id: String { response.imageId }
    }

    /// Save a scan result and its image to the cache
    func save(response: ScanResponse, image: UIImage) {
        guard FeatureFlags.shared.offlineCache else { return }

        let fileName = "\(response.imageId).jpg"
        let fileURL = cacheDirectory.appendingPathComponent(fileName)

        // Save image as JPEG
        if let data = image.jpegData(compressionQuality: 0.6) {
            try? data.write(to: fileURL)
        }

        var entries = entries()
        let entry = CachedScan(
            response: response,
            timestamp: Date(),
            imageFileName: fileName
        )
        entries.insert(entry, at: 0)

        // Evict oldest if over limit
        while entries.count > maxEntries {
            let removed = entries.removeLast()
            let removedURL = cacheDirectory.appendingPathComponent(removed.imageFileName)
            try? FileManager.default.removeItem(at: removedURL)
        }

        saveEntries(entries)
    }

    /// Load all cached scan results (most recent first)
    func loadAll() -> [(response: ScanResponse, image: UIImage?, timestamp: Date)] {
        return entries().compactMap { entry in
            let imageURL = cacheDirectory.appendingPathComponent(entry.imageFileName)
            let image = UIImage(contentsOfFile: imageURL.path)
            return (response: entry.response, image: image, timestamp: entry.timestamp)
        }
    }

    /// Whether there are any cached scans
    var hasCachedScans: Bool {
        !entries().isEmpty
    }

    /// Clear all cached scans
    func clearAll() {
        let entries = entries()
        for entry in entries {
            let fileURL = cacheDirectory.appendingPathComponent(entry.imageFileName)
            try? FileManager.default.removeItem(at: fileURL)
        }
        defaults.removeObject(forKey: cacheKey)
    }

    /// Delete a single cached scan by index
    func delete(at index: Int) {
        var all = entries()
        guard index >= 0, index < all.count else { return }
        let removed = all.remove(at: index)
        let fileURL = cacheDirectory.appendingPathComponent(removed.imageFileName)
        try? FileManager.default.removeItem(at: fileURL)
        saveEntries(all)
    }

    /// Load the full image for a cached scan entry
    func loadImage(for entry: CachedScan) -> UIImage? {
        let url = cacheDirectory.appendingPathComponent(entry.imageFileName)
        return UIImage(contentsOfFile: url.path)
    }

    /// Load a thumbnail for efficient list display using ImageIO
    func loadThumbnail(for entry: CachedScan, maxSize: CGFloat = 60) -> UIImage? {
        let url = cacheDirectory.appendingPathComponent(entry.imageFileName)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceThumbnailMaxPixelSize: maxSize,
            kCGImageSourceCreateThumbnailFromImageAlways: true
        ]
        guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
        return UIImage(cgImage: cgImage)
    }

    /// All cached entries (most recent first), without loading images
    func entries() -> [CachedScan] {
        guard let data = defaults.data(forKey: cacheKey) else { return [] }
        return (try? JSONDecoder().decode([CachedScan].self, from: data)) ?? []
    }

    // MARK: - Private

    private var cacheDirectory: URL {
        let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("scan_cache", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func saveEntries(_ entries: [CachedScan]) {
        if let data = try? JSONEncoder().encode(entries) {
            defaults.set(data, forKey: cacheKey)
        }
    }
}
