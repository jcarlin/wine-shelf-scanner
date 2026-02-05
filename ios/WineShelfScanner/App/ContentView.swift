import SwiftUI

/// Main content view that manages the scan flow
struct ContentView: View {
    @StateObject private var viewModel: ScanViewModel
    @StateObject private var networkMonitor = NetworkMonitor.shared
    @ObservedObject private var subscriptionManager = SubscriptionManager.shared
    @State private var showCamera = false
    @State private var showPhotoPicker = false
    @State private var capturedImage: UIImage?
    @State private var showAbout = false
    @State private var showCachedScans = false
    @State private var showPaywall = false

    /// Whether we're running in UI test mode (bypass photo picker)
    private var isUITesting: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.environment["USE_MOCKS"] == "true"
        #else
        return false
        #endif
    }

    /// Whether the paywall should block scan initiation
    private var shouldShowPaywall: Bool {
        FeatureFlags.shared.subscription
            && ScanCounter.shared.hasReachedLimit
            && !subscriptionManager.isSubscribed
    }

    /// Remaining free scans to display (nil when feature is off or subscribed)
    private var scansRemaining: Int? {
        guard FeatureFlags.shared.subscription,
              !subscriptionManager.isSubscribed else {
            return nil
        }
        return ScanCounter.shared.remaining
    }

    init(viewModel: ScanViewModel? = nil) {
        _viewModel = StateObject(wrappedValue: viewModel ?? Self.createDefaultViewModel())
    }

    /// Create a mock image for UI testing (bypasses photo picker)
    private static func createMockImage() -> UIImage {
        let size = CGSize(width: 400, height: 600)
        UIGraphicsBeginImageContextWithOptions(size, false, 1.0)
        defer { UIGraphicsEndImageContext() }

        UIColor.darkGray.setFill()
        UIRectFill(CGRect(origin: .zero, size: size))

        return UIGraphicsGetImageFromCurrentImageContext() ?? UIImage()
    }

    /// Create the default ScanViewModel, optionally configured for UI testing
    private static func createDefaultViewModel() -> ScanViewModel {
        #if DEBUG
        if ProcessInfo.processInfo.environment["USE_MOCKS"] == "true" {
            let mockService = MockScanService()

            // Configure scenario from environment
            if let scenario = ProcessInfo.processInfo.environment["MOCK_SCENARIO"],
               let mockScenario = MockScanService.MockScenario(rawValue: scenario) {
                mockService.scenario = mockScenario
            }

            // Configure error simulation
            if ProcessInfo.processInfo.environment["SIMULATE_ERROR"] == "true" {
                mockService.shouldSimulateError = true
            }

            // Fast delays for UI tests
            mockService.simulatedDelay = 0.1

            return ScanViewModel(scanService: mockService)
        }
        #endif

        // Default: use real service
        return ScanViewModel()
    }

    /// Attempt to start a scan, showing paywall if limit reached
    private func attemptScan(action: @escaping () -> Void) {
        if shouldShowPaywall {
            showPaywall = true
        } else {
            action()
        }
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Offline banner (persistent, above content)
                    if FeatureFlags.shared.offlineCache && !networkMonitor.isConnected {
                        OfflineBanner()
                    }

                    // Main content
                    switch viewModel.state {
                    case .idle:
                        IdleView(
                            onScanCamera: {
                                attemptScan {
                                    if isUITesting {
                                        let mockImage = Self.createMockImage()
                                        capturedImage = mockImage
                                        viewModel.performScan(with: mockImage)
                                    } else {
                                        showCamera = true
                                    }
                                }
                            },
                            onScanLibrary: {
                                attemptScan {
                                    if isUITesting {
                                        let mockImage = Self.createMockImage()
                                        capturedImage = mockImage
                                        viewModel.performScan(with: mockImage)
                                    } else {
                                        showPhotoPicker = true
                                    }
                                }
                            },
                            onViewCachedScans: {
                                showCachedScans = true
                            },
                            hasCachedScans: viewModel.hasCachedScans,
                            isOffline: FeatureFlags.shared.offlineCache && !networkMonitor.isConnected,
                            scansRemaining: scansRemaining
                        )

                    case .processing:
                        ProcessingView()

                    case .results(let response, let image):
                        ResultsView(
                            response: response,
                            image: image,
                            onNewScan: {
                                viewModel.reset()
                                capturedImage = nil
                            },
                            onToggleDebugMode: {
                                viewModel.toggleDebugMode()
                            },
                            debugMode: viewModel.debugMode
                        )

                    case .cachedResults(let response, let image, let timestamp):
                        VStack(spacing: 0) {
                            CachedResultBanner(timestamp: timestamp)
                            if let image = image {
                                ResultsView(
                                    response: response,
                                    image: image,
                                    onNewScan: {
                                        viewModel.reset()
                                        capturedImage = nil
                                    },
                                    onToggleDebugMode: {
                                        viewModel.toggleDebugMode()
                                    },
                                    debugMode: viewModel.debugMode
                                )
                            } else {
                                // No cached image — show results as fallback list
                                FallbackListView(
                                    wines: response.results.map {
                                        FallbackWine(wineName: $0.wineName, rating: $0.rating)
                                    } + response.fallbackList
                                )
                                HStack {
                                    Button(action: {
                                        viewModel.reset()
                                        capturedImage = nil
                                    }) {
                                        Label("New Scan", systemImage: "camera.fill")
                                            .font(.headline)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .tint(.white)
                                    .accessibilityIdentifier("newScanButton")
                                }
                                .padding()
                                .background(Color.black.opacity(0.9))
                            }
                        }

                    case .error(let message):
                        ErrorView(
                            message: message,
                            onRetry: {
                                if let image = capturedImage {
                                    viewModel.performScan(with: image)
                                } else {
                                    showCamera = true
                                }
                            },
                            onReset: {
                                viewModel.reset()
                                capturedImage = nil
                            },
                            onViewCached: viewModel.hasCachedScans ? {
                                viewModel.showCachedScans()
                            } : nil
                        )
                    }
                }
            }
            .navigationTitle("Wine Scanner")
            .navigationBarTitleDisplayMode(.inline)
            .preferredColorScheme(.dark)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        showAbout = true
                    } label: {
                        Image(systemName: "info.circle")
                            .foregroundColor(.white.opacity(0.7))
                    }
                    .accessibilityIdentifier("aboutButton")
                }
            }
            .sheet(isPresented: $showCamera) {
                CameraView(image: $capturedImage, isPresented: $showCamera)
                    .ignoresSafeArea()
            }
            .sheet(isPresented: $showPhotoPicker) {
                PhotoPicker(image: $capturedImage, isPresented: $showPhotoPicker)
                    .ignoresSafeArea()
            }
            .sheet(isPresented: $showAbout) {
                AboutView()
                    .presentationDetents([.medium])
            }
            .sheet(isPresented: $showCachedScans) {
                CachedScansView(viewModel: viewModel)
            }
            .sheet(isPresented: $showPaywall) {
                PaywallView(subscriptionManager: subscriptionManager)
            }
            .onChange(of: capturedImage) { newImage in
                if let image = newImage {
                    viewModel.performScan(with: image)
                }
            }
        }
    }
}

// MARK: - Offline Banner

/// Persistent banner shown when device is offline
struct OfflineBanner: View {
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "wifi.slash")
                .font(.caption)
            Text("Offline")
                .font(.caption)
                .fontWeight(.medium)
        }
        .foregroundColor(.white.opacity(0.9))
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(Color.orange.opacity(0.8))
        .accessibilityIdentifier("offlineBanner")
    }
}

// MARK: - Cached Result Banner

/// Banner indicating results are from cache, with relative timestamp
struct CachedResultBanner: View {
    let timestamp: Date

    private var relativeTime: String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: timestamp, relativeTo: Date())
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.caption)
            Text("Cached \(relativeTime)")
                .font(.caption)
                .fontWeight(.medium)
        }
        .foregroundColor(.white.opacity(0.9))
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(Color.blue.opacity(0.7))
        .accessibilityIdentifier("cachedResultBanner")
    }
}

// MARK: - Supporting Views

struct IdleView: View {
    let onScanCamera: () -> Void
    let onScanLibrary: () -> Void
    var onViewCachedScans: (() -> Void)? = nil
    var hasCachedScans: Bool = false
    var isOffline: Bool = false
    var scansRemaining: Int? = nil

    @State private var cameraAvailable = UIImagePickerController.isSourceTypeAvailable(.camera)

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "camera.viewfinder")
                .font(.system(size: 80))
                .foregroundColor(.white.opacity(0.7))

            Text("Never guess at the wine shelf again.")
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            Text("Ratings from 21 million reviews — on every bottle, instantly.")
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            VStack(spacing: 12) {
                if cameraAvailable {
                    Button(action: onScanCamera) {
                        Label("Scan Shelf", systemImage: "camera.fill")
                            .font(.headline)
                            .foregroundColor(.black)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(Color.white)
                            .cornerRadius(12)
                    }
                    .accessibilityIdentifier("scanShelfButton")
                    .padding(.horizontal, 40)
                }

                Button(action: onScanLibrary) {
                    Label(cameraAvailable ? "Choose Photo" : "Select Photo", systemImage: "photo.on.rectangle")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.white.opacity(0.2))
                        .cornerRadius(12)
                }
                .accessibilityIdentifier("choosePhotoButton")
                .padding(.horizontal, 40)

                // Recent scans button — shown when cache has entries
                if hasCachedScans, let onViewCachedScans = onViewCachedScans {
                    Button(action: onViewCachedScans) {
                        Label("Recent Scans", systemImage: "clock.arrow.circlepath")
                            .font(.headline)
                            .foregroundColor(.white)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .background(Color.white.opacity(0.12))
                            .cornerRadius(12)
                    }
                    .accessibilityIdentifier("recentScansButton")
                    .padding(.horizontal, 40)
                }
            }
            .padding(.top, 16)

            // Free scans remaining indicator
            if let remaining = scansRemaining, remaining > 0 {
                HStack(spacing: 4) {
                    Image(systemName: "sparkles")
                        .font(.caption2)
                    Text("\(remaining) free scan\(remaining == 1 ? "" : "s") remaining")
                }
                .font(.caption)
                .foregroundColor(.white.opacity(remaining <= 2 ? 0.6 : 0.4))
                .padding(.top, 4)
                .accessibilityIdentifier("scansRemainingLabel")
            }
        }
    }
}

struct ProcessingView: View {
    private let tips = [
        "Tap any rating badge to see details",
        "Top-rated bottles get a gold highlight",
        "Powered by 21 million aggregated reviews",
        "We cover 181,000+ wines worldwide",
    ]

    @State private var currentTipIndex = 0
    let timer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
                .tint(.white)
                .accessibilityIdentifier("processingSpinner")

            Text("Analyzing wines...")
                .font(.headline)
                .foregroundColor(.white)

            Text(tips[currentTipIndex])
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.5))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .id(currentTipIndex)
                .transition(.opacity)
                .animation(.easeInOut(duration: 0.5), value: currentTipIndex)
        }
        .onReceive(timer) { _ in
            currentTipIndex = (currentTipIndex + 1) % tips.count
        }
    }
}

struct ErrorView: View {
    let message: String
    let onRetry: () -> Void
    let onReset: () -> Void
    var onViewCached: (() -> Void)? = nil

    @State private var showBugReport = false

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 60))
                .foregroundColor(.yellow)

            Text(message)
                .font(.headline)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
                .accessibilityIdentifier("errorMessage")

            HStack(spacing: 16) {
                Button("Try Again", action: onRetry)
                    .buttonStyle(.bordered)
                    .tint(.white)
                    .accessibilityIdentifier("retryButton")

                Button("Start Over", action: onReset)
                    .buttonStyle(.borderedProminent)
                    .tint(.white)
                    .accessibilityIdentifier("startOverButton")
            }

            // Cache fallback button — shown when cached scans are available
            if let onViewCached = onViewCached {
                Button(action: onViewCached) {
                    Label("View Recent Scans", systemImage: "clock.arrow.circlepath")
                        .font(.subheadline)
                }
                .buttonStyle(.bordered)
                .tint(.orange)
                .accessibilityIdentifier("viewCachedScansButton")
            }

            if FeatureFlags.shared.bugReport {
                Button {
                    showBugReport = true
                } label: {
                    Label("Report an Issue", systemImage: "flag")
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.6))
                }
                .accessibilityIdentifier("reportBugButton")
            }
        }
        .accessibilityIdentifier("errorView")
        .sheet(isPresented: $showBugReport) {
            BugReportSheet(
                reportType: .error,
                errorMessage: message,
                imageId: nil,
                metadata: nil
            )
            .presentationDetents([.medium])
        }
    }
}

// MARK: - About View

struct AboutView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Image(systemName: "wineglass.fill")
                    .font(.system(size: 48))
                    .foregroundColor(Color(red: 0.45, green: 0.18, blue: 0.22))

                Text("Wine Shelf Scanner")
                    .font(.title2)
                    .fontWeight(.bold)

                Text("Ratings aggregated from 21 million reviews across community wine platforms. Individual scores are combined to provide a single trusted rating for each bottle.")
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                VStack(alignment: .leading, spacing: 8) {
                    Label("181,000+ wines with ratings", systemImage: "checkmark.circle.fill")
                        .foregroundColor(.secondary)
                    Label("21 million aggregated reviews", systemImage: "star.fill")
                        .foregroundColor(.secondary)
                }
                .font(.subheadline)

                Spacer()

                Text("Ratings sourced from community wine platforms. Wine Shelf Scanner is not affiliated with any rating provider.")
                    .font(.caption)
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .padding(.top, 32)
            .padding(.horizontal)
            .navigationTitle("About")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
