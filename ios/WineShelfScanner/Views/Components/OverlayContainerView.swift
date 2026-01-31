import SwiftUI

/// Container view that positions rating badges over the image
struct OverlayContainerView: View {
    let response: ScanResponse
    let containerSize: CGSize
    let onWineTapped: (WineResult) -> Void

    var body: some View {
        ZStack {
            ForEach(response.visibleResults) { wine in
                RatingBadge(
                    rating: wine.rating,
                    confidence: wine.confidence,
                    isTopThree: response.isTopThree(wine),
                    isTappable: wine.isTappable,
                    wineName: wine.wineName
                )
                .position(
                    OverlayMath.adjustedAnchorPoint(
                        OverlayMath.anchorPoint(bbox: wine.bbox, geo: containerSize),
                        bbox: wine.bbox.cgRect,
                        geo: containerSize,
                        badgeSize: OverlayMath.badgeSize(isTopThree: response.isTopThree(wine))
                    )
                )
                .opacity(OverlayMath.opacity(confidence: wine.confidence))
                .onTapGesture {
                    onWineTapped(wine)
                }
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
            containerSize: CGSize(width: 400, height: 600),
            onWineTapped: { _ in }
        )
    }
    .frame(width: 400, height: 600)
}
