import Foundation

/// Feature flags backed by UserDefaults.
///
/// Defaults are compiled in. Override at runtime via:
/// - Debug settings UI (dev builds)
/// - UserDefaults.standard.set(true, forKey: "feature_wine_memory")
///
/// Upgrade path: Replace UserDefaults reads with Firebase Remote Config
/// or LaunchDarkly SDK calls when remote toggling is needed.
struct FeatureFlags {
    static let shared = FeatureFlags()

    private let defaults = UserDefaults.standard

    private let compiledDefaults: [String: Bool] = [
        "feature_wine_memory": true,
        "feature_shelf_ranking": true,
        "feature_safe_pick": true,
        "feature_pairings": true,
        "feature_trust_signals": true,
        "feature_visual_emphasis": true,
        "feature_offline_cache": true,
        "feature_share": true,
        "feature_bug_report": true,
    ]

    var wineMemory: Bool {
        flagValue("feature_wine_memory")
    }

    var shelfRanking: Bool {
        flagValue("feature_shelf_ranking")
    }

    var safePick: Bool {
        flagValue("feature_safe_pick")
    }

    var pairings: Bool {
        flagValue("feature_pairings")
    }

    var trustSignals: Bool {
        flagValue("feature_trust_signals")
    }

    var visualEmphasis: Bool {
        flagValue("feature_visual_emphasis")
    }

    var offlineCache: Bool {
        flagValue("feature_offline_cache")
    }

    var share: Bool {
        flagValue("feature_share")
    }

    var bugReport: Bool {
        flagValue("feature_bug_report")
    }

    /// Returns UserDefaults override if set, otherwise compiled default.
    private func flagValue(_ key: String) -> Bool {
        if defaults.object(forKey: key) != nil {
            return defaults.bool(forKey: key)
        }
        return compiledDefaults[key] ?? false
    }

    /// Override a flag at runtime (debug builds).
    func setOverride(_ key: String, value: Bool) {
        defaults.set(value, forKey: key)
    }

    /// Remove runtime override, revert to compiled default.
    func removeOverride(_ key: String) {
        defaults.removeObject(forKey: key)
    }
}
