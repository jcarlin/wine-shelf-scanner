import Foundation
import Network

/// Monitors network connectivity using Apple's NWPathMonitor.
///
/// Publishes connection state for SwiftUI views to react to.
/// All monitoring is gated behind the `feature_offline_cache` flag.
///
/// Usage:
///   @StateObject private var networkMonitor = NetworkMonitor.shared
///   if !networkMonitor.isConnected { ... }
final class NetworkMonitor: ObservableObject {
    static let shared = NetworkMonitor()

    @Published private(set) var isConnected: Bool = true
    @Published private(set) var isExpensive: Bool = false
    @Published private(set) var isConstrained: Bool = false

    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "NetworkMonitor")
    private var started = false

    /// Whether the device is on a metered or constrained connection
    var shouldReduceData: Bool {
        isExpensive || isConstrained
    }

    /// JPEG compression quality adapted to network conditions
    var compressionQuality: CGFloat {
        shouldReduceData ? 0.5 : 0.8
    }

    init() {
        start()
    }

    func start() {
        guard !started else { return }
        guard FeatureFlags.shared.offlineCache else { return }

        started = true
        monitor.pathUpdateHandler = { [weak self] path in
            DispatchQueue.main.async {
                self?.isConnected = path.status == .satisfied
                self?.isExpensive = path.isExpensive
                self?.isConstrained = path.isConstrained
            }
        }
        monitor.start(queue: queue)
    }

    func stop() {
        guard started else { return }
        monitor.cancel()
        started = false
    }
}
