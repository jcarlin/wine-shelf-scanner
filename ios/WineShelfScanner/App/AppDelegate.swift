import UIKit

/// App delegate adapter for handling background URLSession events.
///
/// When iOS completes a background upload after the app was terminated,
/// it relaunches the app and calls `application(_:handleEventsForBackgroundURLSession:completionHandler:)`.
/// This delegate forwards that call to `BackgroundScanManager`.
class AppDelegate: NSObject, UIApplicationDelegate {

    func application(
        _ application: UIApplication,
        handleEventsForBackgroundURLSession identifier: String,
        completionHandler: @escaping () -> Void
    ) {
        guard identifier == BackgroundScanManager.sessionIdentifier else {
            completionHandler()
            return
        }
        BackgroundScanManager.shared.handleBackgroundSessionEvents(completionHandler: completionHandler)
    }
}
