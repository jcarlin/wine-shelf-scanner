import Foundation

/// Tracks the number of successful scans for paywall enforcement.
///
/// Only counts successful scans (API errors and empty results do not count).
/// Gated by `FeatureFlags.shared.subscription` — counting only occurs when enabled.
class ScanCounter {
    static let shared = ScanCounter()

    static let freeLimit = 5

    private let key = "successful_scan_count"
    private let defaults = UserDefaults.standard

    /// Total number of successful scans recorded.
    var count: Int {
        defaults.integer(forKey: key)
    }

    /// Number of free scans remaining before paywall.
    var remaining: Int {
        max(0, Self.freeLimit - count)
    }

    /// Whether the user has used all free scans.
    var hasReachedLimit: Bool {
        count >= Self.freeLimit
    }

    /// Record a successful scan. Only call when `FeatureFlags.shared.subscription` is on.
    func increment() {
        defaults.set(count + 1, forKey: key)
    }

    /// Reset counter (for testing).
    func reset() {
        defaults.removeObject(forKey: key)
    }
}
