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

    var body: some View {
        VStack(spacing: 0) {
            // Show fallback list if full failure, otherwise show overlay view
            if response.isFullFailure {
                FallbackListView(wines: response.fallbackList)
            } else {
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
            WineDetailSheet(wine: wine)
                .presentationDetents([.height(200)])
        }
        .onAppear {
            if response.isPartialDetection {
                showToast = true
                // Cancel any pending dismissal
                toastWorkItem?.cancel()
                // Auto-dismiss after 3 seconds
                let workItem = DispatchWorkItem { [self] in
                    showToast = false
                }
                toastWorkItem = workItem
                DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: workItem)
            }
        }
        .onDisappear {
            // Cancel pending dismissal when view disappears
            toastWorkItem?.cancel()
            toastWorkItem = nil
        }
        .overlay(alignment: .top) {
            if showToast {
                ToastView(message: "Some bottles couldn't be recognized")
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .animation(.easeInOut, value: showToast)
                    .accessibilityIdentifier("partialDetectionToast")
            }
        }
    }

    private var overlayImageView: some View {
        GeometryReader { geo in
            ZStack {
                // Wine shelf image
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                // Rating overlays
                OverlayContainerView(
                    response: response,
                    containerSize: geo.size,
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
                Label("New Scan", systemImage: "camera.fill")
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
}

/// Toast notification view
struct ToastView: View {
    let message: String

    var body: some View {
        Text(message)
            .font(.subheadline)
            .foregroundColor(.white)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.black.opacity(0.8))
            .cornerRadius(8)
            .padding(.top, 8)
    }
}

/// Fallback list view when no bottles detected
struct FallbackListView: View {
    let wines: [FallbackWine]

    var sortedWines: [FallbackWine] {
        wines.sorted { ($0.rating ?? 0) > ($1.rating ?? 0) }
    }

    var body: some View {
        VStack(spacing: 0) {
            Text("Wines Found")
                .font(.headline)
                .foregroundColor(.white)
                .padding()
                .accessibilityIdentifier("fallbackListHeader")

            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(sortedWines) { wine in
                        FallbackWineRow(wine: wine)
                    }
                }
                .padding()
            }
            .accessibilityIdentifier("fallbackList")
        }
        .accessibilityIdentifier("fallbackContainer")
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
