import SwiftUI

/// Application state for the scan flow
enum ScanState: Equatable {
    case idle
    case processing
    case results(ScanResponse, UIImage)
    case error(String)

    static func == (lhs: ScanState, rhs: ScanState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle):
            return true
        case (.processing, .processing):
            return true
        case (.results(let r1, _), .results(let r2, _)):
            return r1 == r2
        case (.error(let e1), .error(let e2)):
            return e1 == e2
        default:
            return false
        }
    }
}
