import Foundation

/// Sentiment for a remembered wine
enum WineSentiment: String, Codable {
    case liked
    case disliked
}

/// A single wine memory entry
struct WineMemoryEntry: Codable {
    let wineName: String
    let sentiment: WineSentiment
    let timestamp: Date

    enum CodingKeys: String, CodingKey {
        case wineName = "wine_name"
        case sentiment
        case timestamp
    }
}

/// Device-local wine memory store backed by UserDefaults
///
/// Stores up to 500 wine sentiments (liked/disliked) keyed by
/// lowercase wine name. LRU eviction when limit is reached.
final class WineMemoryStore {
    static let shared = WineMemoryStore()

    private let userDefaultsKey = "wine_memory"
    private let maxEntries = 500
    private let defaults: UserDefaults
    private var cache: [String: WineMemoryEntry] = [:]
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        decoder.dateDecodingStrategy = .iso8601
        encoder.dateEncodingStrategy = .iso8601
        loadCache()
    }

    /// Save a sentiment for a wine (latest write wins)
    func save(wineName: String, sentiment: WineSentiment) {
        let key = wineName.lowercased()
        let entry = WineMemoryEntry(
            wineName: wineName,
            sentiment: sentiment,
            timestamp: Date()
        )
        cache[key] = entry
        evictIfNeeded()
        persist()
    }

    /// Get the sentiment for a wine, if remembered
    func get(wineName: String) -> WineSentiment? {
        let key = wineName.lowercased()
        return cache[key]?.sentiment
    }

    /// Clear a specific wine from memory
    func clear(wineName: String) {
        let key = wineName.lowercased()
        cache.removeValue(forKey: key)
        persist()
    }

    /// Get all stored entries
    func allEntries() -> [WineMemoryEntry] {
        Array(cache.values)
    }

    // MARK: - Private

    private func loadCache() {
        guard let data = defaults.data(forKey: userDefaultsKey),
              let entries = try? decoder.decode([String: WineMemoryEntry].self, from: data) else {
            return
        }
        cache = entries
    }

    private func persist() {
        guard let data = try? encoder.encode(cache) else { return }
        defaults.set(data, forKey: userDefaultsKey)
    }

    private func evictIfNeeded() {
        guard cache.count > maxEntries else { return }
        // LRU eviction: remove oldest entries
        let sorted = cache.sorted { $0.value.timestamp < $1.value.timestamp }
        let toRemove = cache.count - maxEntries
        for (key, _) in sorted.prefix(toRemove) {
            cache.removeValue(forKey: key)
        }
    }
}
