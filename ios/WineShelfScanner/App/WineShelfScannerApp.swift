import SwiftUI

@main
struct WineShelfScannerApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .onAppear {
                    // Configure notification service on launch
                    NotificationService.shared.configure()

                    // Proactively request notification permission
                    if FeatureFlags.shared.backgroundProcessing {
                        Task {
                            await NotificationService.shared.requestPermission()
                        }
                    }
                }
        }
    }
}
