
import SwiftUI

struct OverlayMath {
    static func anchorPoint(bbox: CGRect, geo: CGSize) -> CGPoint {
        let x = (bbox.origin.x + bbox.size.width / 2) * geo.width
        let y = (bbox.origin.y + bbox.size.height * 0.25) * geo.height
        return CGPoint(x: x, y: y)
    }

    static func opacity(confidence: Double) -> Double {
        switch confidence {
        case 0.85...1.0: return 1.0
        case 0.65..<0.85: return 0.75
        case 0.45..<0.65: return 0.5
        default: return 0.0
        }
    }
}
