import SwiftUI

/// Displays scan results with overlays on the image
struct ResultsView: View {
    let response: ScanResponse
    let image: UIImage
    let onNewScan: () -> Void
    let onToggleDebugMode: () -> Void
    let debugMode: Bool

    @State private var selectedWine: WineResult?
    @State private var showToast = false
    @State private var toastWorkItem: DispatchWorkItem?
    @State private var showBugReport = false

    /// Compute shelf rankings for detail sheet (rank by rating, ties share rank)
    private var shelfRankingsForDetail: [String: (rank: Int, total: Int)] {
        guard FeatureFlags.shared.shelfRanking else { return [:] }
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
        VStack(spacing: 0) {
            // Show fallback list if full failure, otherwise show overlay view
            if response.isFullFailure {
                FallbackListView(wines: response.fallbackList)
            } else {
                resultsSummaryHeader
                overlayImageView
            }

            // Debug tray (when debug data present)
            if let debugData = response.debug {
                DebugTray(debugData: debugData)
            }

            // Bottom action bar
            bottomBar
        }
        .accessibilityIdentifier("resultsView")
        .sheet(item: $selectedWine) { wine in
            let rankings = shelfRankingsForDetail
            WineDetailSheet(
                wine: wine,
                imageId: response.imageId,
                shelfRank: rankings[wine.id]?.rank,
                shelfTotal: rankings[wine.id]?.total
            )
            .presentationDetents([.height(280)])
        }
        .onAppear {
            if response.isPartialDetection {
                showToast = true
                // Cancel any pending dismissal
                toastWorkItem?.cancel()
                // Auto-dismiss after 6 seconds
                let workItem = DispatchWorkItem { [self] in
                    showToast = false
                }
                toastWorkItem = workItem
                DispatchQueue.main.asyncAfter(deadline: .now() + 6, execute: workItem)
            }
        }
        .onDisappear {
            // Cancel pending dismissal when view disappears
            toastWorkItem?.cancel()
            toastWorkItem = nil
        }
        // Partial detection toast — disabled: we should never tell users
        // "some bottles couldn't be recognized", just show what we found.
        // .overlay(alignment: .top) {
        //     if showToast {
        //         HStack(spacing: 8) {
        //             ToastView(message: NSLocalizedString("results.partialDetection", comment: "Partial detection toast"))
        //             if FeatureFlags.shared.bugReport {
        //                 Button {
        //                     showBugReport = true
        //                 } label: {
        //                     Text(NSLocalizedString("bugReport.report", comment: "Report button"))
        //                         .font(.footnote)
        //                         .fontWeight(.semibold)
        //                         .foregroundColor(.yellow.opacity(0.7))
        //                         .underline()
        //                 }
        //                 .accessibilityIdentifier("partialDetectionReportButton")
        //             }
        //         }
        //         .padding(.horizontal, 8)
        //         .transition(.move(edge: .top).combined(with: .opacity))
        //         .animation(.easeInOut, value: showToast)
        //         .accessibilityIdentifier("partialDetectionToast")
        //     }
        // }
        .sheet(isPresented: $showBugReport) {
            BugReportSheet(
                reportType: response.isFullFailure ? .fullFailure : .partialDetection,
                errorMessage: nil,
                imageId: response.imageId,
                metadata: BugReportMetadata(
                    winesDetected: response.visibleResults.count,
                    winesInFallback: response.fallbackList.count,
                    confidenceScores: response.results.map { $0.confidence }
                )
            )
            .presentationDetents([.medium])
        }
    }

    private var resultsSummaryHeader: some View {
        let visible = response.visibleResults
        let topWine = response.topRatedResults.first

        return HStack(spacing: 6) {
            if let top = topWine, top.rating != nil {
                Image(systemName: "star.fill")
                    .foregroundColor(.yellow)
                    .font(.caption)
                Text(top.wineName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundColor(.white)
                    .lineLimit(1)
                if visible.count > 1 {
                    Text("+ \(visible.count - 1) more")
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.5))
                }
            } else {
                Text("\(visible.count) bottle\(visible.count != 1 ? "s" : "") found")
                    .font(.subheadline)
                    .foregroundColor(.white.opacity(0.7))
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity)
        .background(Color.black.opacity(0.9))
        .accessibilityIdentifier("resultsSummaryHeader")
    }

    private var overlayImageView: some View {
        GeometryReader { geo in
            let imageBounds = OverlayMath.getImageBounds(
                imageSize: image.size,
                containerSize: geo.size
            )

            ZStack {
                // Wine shelf image
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                // Rating overlays (positioned relative to actual image bounds)
                OverlayContainerView(
                    response: response,
                    imageBounds: imageBounds,
                    onWineTapped: { wine in
                        if wine.isTappable {
                            selectedWine = wine
                        }
                    }
                )
            }
        }
    }

    private var bottomBar: some View {
        HStack {
            Button(action: onNewScan) {
                Label(NSLocalizedString("results.newScan", comment: "New scan button"), systemImage: "camera.fill")
                    .font(.headline)
            }
            .buttonStyle(.borderedProminent)
            .tint(.white)
            .accessibilityIdentifier("newScanButton")
            .simultaneousGesture(
                LongPressGesture(minimumDuration: 1.0)
                    .onEnded { _ in
                        onToggleDebugMode()
                    }
            )

            // Share shelf results
            if FeatureFlags.shared.share {
                Button {
                    shareShelfResults()
                } label: {
                    Image(systemName: "square.and.arrow.up")
                        .font(.headline)
                        .foregroundColor(.white)
                }
                .accessibilityIdentifier("shareShelfButton")
            }

            // Debug mode indicator
            if debugMode {
                Image(systemName: "wrench.and.screwdriver.fill")
                    .foregroundColor(.orange)
                    .font(.caption)
            }
        }
        .padding()
        .background(Color.black.opacity(0.9))
    }

    private func shareShelfResults() {
        let topWines = response.topRatedResults.prefix(3)
        var text = NSLocalizedString("results.topPicks", comment: "Share text header") + "\n"
        let starsLabel = NSLocalizedString("results.stars", comment: "Stars label")
        for (index, wine) in topWines.enumerated() {
            let ratingStr = wine.rating.map { String(format: "%.1f", $0) } ?? "?"
            text += "\(index + 1). \(wine.wineName) - \(ratingStr) \(starsLabel)\n"
        }
        text += "\n" + NSLocalizedString("results.scannedWith", comment: "Share attribution")

        let activityVC = UIActivityViewController(activityItems: [text], applicationActivities: nil)
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let root = windowScene.windows.first?.rootViewController {
            if let popover = activityVC.popoverPresentationController {
                popover.sourceView = root.view
                popover.sourceRect = CGRect(x: root.view.bounds.midX, y: root.view.bounds.midY, width: 0, height: 0)
                popover.permittedArrowDirections = []
            }
            root.present(activityVC, animated: true)
        }
    }
}

/// Toast notification view
struct ToastView: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.subheadline)
            .fontWeight(.medium)
            .foregroundColor(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.black.opacity(0.85))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.yellow.opacity(0.25), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.3), radius: 8, y: 4)
            .padding(.top, 8)
    }
}

/// Fallback list view when no bottles detected
struct FallbackListView: View {
    let wines: [FallbackWine]

    @State private var showBugReport = false

    var sortedWines: [FallbackWine] {
        wines.sorted { ($0.rating ?? 0) > ($1.rating ?? 0) }
    }

    var body: some View {
        VStack(spacing: 0) {
            Text(NSLocalizedString("results.winesFound", comment: "Fallback list header"))
                .font(.headline)
                .foregroundColor(.white)
                .padding()
                .accessibilityIdentifier("fallbackListHeader")

            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(sortedWines) { wine in
                        FallbackWineRow(wine: wine)
                    }

                    if FeatureFlags.shared.bugReport {
                        Button {
                            showBugReport = true
                        } label: {
                            Label("Not what you expected? Report an issue", systemImage: "flag")
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.35))
                        }
                        .padding(.top, 8)
                        .accessibilityIdentifier("fallbackReportButton")
                    }
                }
                .padding()
            }
            .accessibilityIdentifier("fallbackList")
        }
        .accessibilityIdentifier("fallbackContainer")
        .sheet(isPresented: $showBugReport) {
            BugReportSheet(
                reportType: .fullFailure,
                errorMessage: nil,
                imageId: nil,
                metadata: BugReportMetadata(
                    winesDetected: 0,
                    winesInFallback: wines.count,
                    confidenceScores: nil
                )
            )
            .presentationDetents([.medium])
        }
    }
}

/// Row in fallback list
struct FallbackWineRow: View {
    let wine: FallbackWine

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(wine.wineName)
                    .font(.body)
                    .foregroundColor(.white)
            }

            Spacer()

            HStack(spacing: 4) {
                Image(systemName: "star.fill")
                    .foregroundColor(.yellow)
                Text(wine.rating.map { String(format: "%.1f", $0) } ?? "—")
                    .font(.headline)
                    .foregroundColor(.white)
            }
        }
        .padding()
        .background(Color.white.opacity(0.1))
        .cornerRadius(8)
    }
}

#Preview("Full Results") {
    let mockService = MockScanService()
    mockService.scenario = .fullShelf

    return ResultsView(
        response: ScanResponse(
            imageId: "preview",
            results: [
                WineResult(wineName: "Opus One", rating: 4.8, confidence: 0.91, bbox: BoundingBox(x: 0.15, y: 0.12, width: 0.09, height: 0.38)),
                WineResult(wineName: "Caymus", rating: 4.5, confidence: 0.94, bbox: BoundingBox(x: 0.05, y: 0.15, width: 0.08, height: 0.35)),
            ],
            fallbackList: [],
            debug: nil
        ),
        image: UIImage(systemName: "photo")!,
        onNewScan: {},
        onToggleDebugMode: {},
        debugMode: false
    )
}
