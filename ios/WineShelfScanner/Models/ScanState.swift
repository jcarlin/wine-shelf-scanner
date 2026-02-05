import SwiftUI

/// Application state for the scan flow
enum ScanState: Equatable {
    case idle
    case processing
    case backgroundProcessing(Date)
    case results(ScanResponse, UIImage)
    case error(String)

    static func == (lhs: ScanState, rhs: ScanState) -> Bool {
        switch (lhs, rhs) {
        case (.idle, .idle):
            return true
        case (.processing, .processing):
            return true
        case (.backgroundProcessing(let d1), .backgroundProcessing(let d2)):
            return d1 == d2
        case (.results(let r1, _), .results(let r2, _)):
            return r1 == r2
        case (.error(let e1), .error(let e2)):
            return e1 == e2
        default:
            return false
        }
    }
}
