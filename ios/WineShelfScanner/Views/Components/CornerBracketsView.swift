import SwiftUI

/// Draws "L"-shaped corner brackets around a wine bottle's bounding box
struct CornerBracketsView: View {
    let bbox: BoundingBox
    let imageBounds: CGRect
    let isBestPick: Bool

    private static let bracketColor = Color(red: 1.0, green: 0.8, blue: 0.0)
    private static let normalOpacity: Double = 0.7
    private static let bestPickOpacity: Double = 0.85
    private static let normalLineWidth: CGFloat = 2
    private static let bestPickLineWidth: CGFloat = 3

    var body: some View {
        Canvas { context, _ in
            let lines = OverlayMath.cornerBrackets(bbox: bbox, geo: imageBounds.size)
            let color = Self.bracketColor.opacity(isBestPick ? Self.bestPickOpacity : Self.normalOpacity)
            let lineWidth = isBestPick ? Self.bestPickLineWidth : Self.normalLineWidth

            for line in lines {
                var path = Path()
                path.move(to: CGPoint(
                    x: imageBounds.origin.x + line.x1,
                    y: imageBounds.origin.y + line.y1
                ))
                path.addLine(to: CGPoint(
                    x: imageBounds.origin.x + line.x2,
                    y: imageBounds.origin.y + line.y2
                ))
                context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
            }
        }
        .allowsHitTesting(false)
    }
}

#Preview {
    ZStack {
        Color.gray
        CornerBracketsView(
            bbox: BoundingBox(x: 0.2, y: 0.2, width: 0.15, height: 0.4),
            imageBounds: CGRect(x: 0, y: 0, width: 400, height: 600),
            isBestPick: true
        )
    }
    .frame(width: 400, height: 600)
}
