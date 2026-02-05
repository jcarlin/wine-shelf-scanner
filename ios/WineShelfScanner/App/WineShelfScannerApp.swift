import SwiftUI

@main
struct WineShelfScannerApp: App {
    /// Keep a reference so the transaction listener stays alive for the app lifetime.
    @StateObject private var subscriptionManager = SubscriptionManager.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
