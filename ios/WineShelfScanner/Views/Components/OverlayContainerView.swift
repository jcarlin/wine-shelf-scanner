import SwiftUI

/// Container view that positions rating badges over the image
struct OverlayContainerView: View {
    let response: ScanResponse
    let imageBounds: CGRect
    let onWineTapped: (WineResult) -> Void

    var body: some View {
        ZStack {
            ForEach(response.visibleResults) { wine in
                let isTopThree = response.isTopThree(wine)
                let badgeSize = OverlayMath.badgeSize(isTopThree: isTopThree)

                // Calculate anchor relative to image bounds, then offset by imageBounds origin
                let anchor = OverlayMath.anchorPoint(bbox: wine.bbox, geo: imageBounds.size)
                let adjusted = OverlayMath.adjustedAnchorPoint(
                    anchor,
                    bbox: wine.bbox.cgRect,
                    geo: imageBounds.size,
                    badgeSize: badgeSize
                )
                let finalPosition = CGPoint(
                    x: imageBounds.origin.x + adjusted.x,
                    y: imageBounds.origin.y + adjusted.y
                )

                RatingBadge(
                    rating: wine.rating,
                    confidence: wine.confidence,
                    isTopThree: isTopThree,
                    isTappable: wine.isTappable,
                    wineName: wine.wineName
                )
                .position(finalPosition)
                .opacity(OverlayMath.opacity(confidence: wine.confidence))
                .onTapGesture {
                    if wine.isTappable {
                        onWineTapped(wine)
                    }
                }
                .allowsHitTesting(wine.isTappable)
            }
        }
        .accessibilityIdentifier("overlayContainer")
    }
}

#Preview {
    let testResponse = ScanResponse(
        imageId: "test",
        results: [
            WineResult(wineName: "Opus One", rating: 4.8, confidence: 0.91, bbox: BoundingBox(x: 0.2, y: 0.2, width: 0.15, height: 0.4)),
            WineResult(wineName: "Caymus", rating: 4.5, confidence: 0.88, bbox: BoundingBox(x: 0.5, y: 0.2, width: 0.15, height: 0.4)),
            WineResult(wineName: "Budget Wine", rating: 3.2, confidence: 0.55, bbox: BoundingBox(x: 0.8, y: 0.2, width: 0.15, height: 0.4)),
        ],
        fallbackList: [],
        debug: nil
    )

    ZStack {
        Color.gray
        OverlayContainerView(
            response: testResponse,
            imageBounds: CGRect(x: 0, y: 0, width: 400, height: 600),
            onWineTapped: { _ in }
        )
    }
    .frame(width: 400, height: 600)
}
