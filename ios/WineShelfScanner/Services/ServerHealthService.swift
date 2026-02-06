import Foundation
import Combine

/// Observable service that checks server health on launch and polls until ready.
///
/// Designed for Cloud Run cold-start scenarios where minInstances=0 and the
/// backend needs time to spin up. Mirrors the Next.js `useServerHealth` hook.
@MainActor
class ServerHealthService: ObservableObject {
    enum State: Equatable {
        case checking
        case warmingUp(attempt: Int)
        case ready
        case unavailable(message: String)

        static func == (lhs: State, rhs: State) -> Bool {
            switch (lhs, rhs) {
            case (.checking, .checking): return true
            case (.warmingUp(let a), .warmingUp(let b)): return a == b
            case (.ready, .ready): return true
            case (.unavailable(let a), .unavailable(let b)): return a == b
            default: return false
            }
        }
    }

    @Published private(set) var state: State = .checking

    private let scanService: ScanServiceProtocol
    private let maxRetryAttempts = 30
    private let confirmationChecks = 2
    private let confirmationInterval: UInt64 = 3_000_000_000 // 3 seconds
    private var checkTask: Task<Void, Never>?

    init(scanService: ScanServiceProtocol) {
        self.scanService = scanService
    }

    /// Start health checking. Call on app launch.
    func start() {
        checkTask?.cancel()
        state = .checking
        checkTask = Task { await doCheck(attempt: 1) }
    }

    /// Retry after unavailable state.
    func retry() {
        start()
    }

    private func doCheck(attempt: Int) async {
        guard !Task.isCancelled else { return }

        let result = await scanService.checkHealth()

        switch result {
        case .healthy:
            state = .warmingUp(attempt: attempt)
            // Confirmation checks to ensure server is truly stable
            let stable = await confirmReady(remaining: confirmationChecks)
            if stable {
                state = .ready
            } else {
                try? await Task.sleep(nanoseconds: 10_000_000_000) // 10s
                await doCheck(attempt: attempt + 1)
            }

        case .warmingUp(let retryAfter):
            if attempt >= maxRetryAttempts {
                state = .unavailable(
                    message: NSLocalizedString("warmup.timeout", comment: "Server timeout message")
                )
                return
            }

            state = .warmingUp(attempt: attempt)

            let delay = min(UInt64(retryAfter) * 1_000_000_000, 10_000_000_000)
            try? await Task.sleep(nanoseconds: delay)
            await doCheck(attempt: attempt + 1)

        case .unavailable(let message):
            state = .unavailable(message: message)
        }
    }

    private func confirmReady(remaining: Int) async -> Bool {
        if remaining <= 0 { return true }
        try? await Task.sleep(nanoseconds: confirmationInterval)
        guard !Task.isCancelled else { return false }
        let check = await scanService.checkHealth()
        guard case .healthy = check else { return false }
        return await confirmReady(remaining: remaining - 1)
    }

    deinit {
        checkTask?.cancel()
    }
}
