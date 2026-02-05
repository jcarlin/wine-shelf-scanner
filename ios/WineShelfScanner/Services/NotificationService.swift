import UserNotifications

/// Manages local notifications for background scan completion.
///
/// Handles permission requests and notification delivery when scans
/// complete while the app is in the background.
final class NotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = NotificationService()

    /// Notification category for scan results
    static let scanCompleteCategory = "SCAN_COMPLETE"
    /// Action to view results from notification
    static let viewResultsAction = "VIEW_RESULTS"

    private override init() {
        super.init()
    }

    // MARK: - Setup

    /// Configure notification categories and set delegate.
    /// Call once at app launch.
    func configure() {
        let viewAction = UNNotificationAction(
            identifier: Self.viewResultsAction,
            title: "View Results",
            options: .foreground
        )

        let category = UNNotificationCategory(
            identifier: Self.scanCompleteCategory,
            actions: [viewAction],
            intentIdentifiers: [],
            options: []
        )

        let center = UNUserNotificationCenter.current()
        center.setNotificationCategories([category])
        center.delegate = self
    }

    // MARK: - Permissions

    /// Request notification permission proactively.
    /// Returns whether permission was granted.
    @discardableResult
    func requestPermission() async -> Bool {
        let center = UNUserNotificationCenter.current()
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .sound, .badge])
            return granted
        } catch {
            return false
        }
    }

    /// Check current authorization status without prompting.
    func isAuthorized() async -> Bool {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        return settings.authorizationStatus == .authorized
    }

    // MARK: - Notifications

    /// Post a local notification that the scan completed successfully.
    func notifyScanComplete(wineCount: Int, bestWine: String?, bestRating: Double?) {
        let content = UNMutableNotificationContent()
        content.title = "Scan Complete"

        if let bestWine = bestWine, let rating = bestRating {
            let ratingStr = String(format: "%.1f", rating)
            content.body = "Found \(wineCount) wine\(wineCount == 1 ? "" : "s") — \(bestWine) rated \(ratingStr)"
        } else {
            content.body = "Found \(wineCount) wine\(wineCount == 1 ? "" : "s"). Tap to see ratings."
        }

        content.sound = .default
        content.categoryIdentifier = Self.scanCompleteCategory

        let request = UNNotificationRequest(
            identifier: "scan-complete-\(UUID().uuidString)",
            content: content,
            trigger: nil // deliver immediately
        )

        UNUserNotificationCenter.current().add(request)
    }

    /// Post a local notification that the scan failed.
    func notifyScanFailed() {
        let content = UNMutableNotificationContent()
        content.title = "Scan Failed"
        content.body = "Your wine shelf scan couldn't be processed. Tap to try again."
        content.sound = .default

        let request = UNNotificationRequest(
            identifier: "scan-failed-\(UUID().uuidString)",
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Show notifications even when app is in foreground (no-op — we suppress
    /// foreground notifications since the user can see results directly).
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // Don't show notification banner if the app is in foreground —
        // the UI will update automatically via BackgroundScanManager's @Published property.
        completionHandler([])
    }

    /// Handle notification tap (bring user to results).
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        // The app will launch/foreground and BackgroundScanManager will
        // restore the completed scan automatically via its @Published property.
        completionHandler()
    }
}
