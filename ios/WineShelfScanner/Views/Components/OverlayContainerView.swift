import SwiftUI

/// Container view that positions rating badges over the image
struct OverlayContainerView: View {
    let response: ScanResponse
    let imageBounds: CGRect
    let onWineTapped: (WineResult) -> Void

    /// Compute shelf rankings for visible wines (rank by rating, ties share rank)
    private var shelfRankings: [String: (rank: Int, total: Int)] {
        let ranked = response.visibleResults
            .filter { $0.rating != nil }
            .sorted { ($0.rating ?? 0) > ($1.rating ?? 0) }

        guard ranked.count >= 3 else { return [:] }

        var rankings: [String: (rank: Int, total: Int)] = [:]
        var currentRank = 1
        for (index, wine) in ranked.enumerated() {
            if index > 0 && wine.rating != ranked[index - 1].rating {
                currentRank = index + 1
            }
            rankings[wine.id] = (rank: currentRank, total: ranked.count)
        }
        return rankings
    }

    var body: some View {
        let showRanking = FeatureFlags.shared.shelfRanking
        let rankings = showRanking ? shelfRankings : [:]
        let showMemory = FeatureFlags.shared.wineMemory

        ZStack {
            if FeatureFlags.shared.cornerBrackets {
                ForEach(response.visibleResults.filter { response.isTopThree($0) }) { wine in
                    CornerBracketsView(
                        bbox: wine.bbox,
                        imageBounds: imageBounds,
                        isBestPick: wine.id == response.topThree.first?.id
                    )
                }
            }

            ForEach(response.visibleResults) { wine in
                let isTopThree = response.isTopThree(wine)
                let badgeSize = OverlayMath.badgeSize(isTopThree: isTopThree)

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

                let ranking = rankings[wine.id]
                let sentiment: WineSentiment? = showMemory
                    ? WineMemoryStore.shared.get(wineName: wine.wineName)
                    : nil

                RatingBadge(
                    rating: wine.rating,
                    confidence: wine.confidence,
                    isTopThree: isTopThree,
                    isTappable: wine.isTappable,
                    wineName: wine.wineName,
                    shelfRank: ranking?.rank,
                    isSafePick: FeatureFlags.shared.safePick && (wine.isSafePick == true),
                    userSentiment: sentiment
                )
                .position(finalPosition)
                .opacity(OverlayMath.opacity(
                    confidence: wine.confidence,
                    isTopThree: isTopThree,
                    visualEmphasis: FeatureFlags.shared.visualEmphasis
                ))
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
