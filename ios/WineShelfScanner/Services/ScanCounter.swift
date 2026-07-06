import Foundation

/// Tracks the number of successful scans in the current calendar month for
/// paywall enforcement.
///
/// Only counts successful scans (API errors and empty results do not count).
/// Gated by `FeatureFlags.shared.subscription` — counting only occurs when enabled.
///
/// The free quota is monthly: the current period key (e.g. "2026-07") is
/// stored alongside the count, and a stale period means the count reads as 0.
class ScanCounter {
    static let shared = ScanCounter()

    static let freeLimit = 5

    private let countKey = "successful_scan_count"
    private let periodStorageKey = "successful_scan_period"
    private let defaults: UserDefaults
    private let now: () -> Date

    init(defaults: UserDefaults = .standard, now: @escaping () -> Date = Date.init) {
        self.defaults = defaults
        self.now = now
    }

    /// Period key ("yyyy-MM") for a date.
    static func periodKey(for date: Date) -> String {
        let components = Calendar.current.dateComponents([.year, .month], from: date)
        return String(format: "%04d-%02d", components.year ?? 0, components.month ?? 0)
    }

    /// Number of successful scans recorded in the current month.
    var count: Int {
        guard defaults.string(forKey: periodStorageKey) == Self.periodKey(for: now()) else {
            return 0
        }
        return defaults.integer(forKey: countKey)
    }

    /// Number of free scans remaining before paywall.
    var remaining: Int {
        max(0, Self.freeLimit - count)
    }

    /// Whether the user has used all free scans this month.
    var hasReachedLimit: Bool {
        count >= Self.freeLimit
    }

    /// Record a successful scan. Only call when `FeatureFlags.shared.subscription` is on.
    func increment() {
        // `count` reads 0 when the stored period is stale, so a month
        // rollover starts the tally fresh.
        let newCount = count + 1
        defaults.set(newCount, forKey: countKey)
        defaults.set(Self.periodKey(for: now()), forKey: periodStorageKey)
    }

    /// Reset counter (for testing).
    func reset() {
        defaults.removeObject(forKey: countKey)
        defaults.removeObject(forKey: periodStorageKey)
    }
}
