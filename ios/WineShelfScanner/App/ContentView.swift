import SwiftUI

/// Main content view that manages the scan flow
struct ContentView: View {
    @StateObject private var viewModel: ScanViewModel
    @ObservedObject private var subscriptionManager = SubscriptionManager.shared
    @State private var showCamera = false
    @State private var showPhotoPicker = false
    @State private var capturedImage: UIImage?
    @State private var showAbout = false
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

                switch viewModel.state {
                case .idle:
                    IdleView(
                        onScanCamera: {
                            attemptScan {
                                if isUITesting {
                                    // Bypass camera, directly trigger scan with mock image
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
                                    // Bypass photo picker, directly trigger scan with mock image
                                    let mockImage = Self.createMockImage()
                                    capturedImage = mockImage
                                    viewModel.performScan(with: mockImage)
                                } else {
                                    showPhotoPicker = true
                                }
                            }
                        },
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
                        }
                    )
                }
            }
            .navigationTitle(NSLocalizedString("app.title", comment: "Navigation title"))
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

// MARK: - Supporting Views

struct IdleView: View {
    let onScanCamera: () -> Void
    let onScanLibrary: () -> Void
    var scansRemaining: Int? = nil

    @State private var cameraAvailable = UIImagePickerController.isSourceTypeAvailable(.camera)

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "camera.viewfinder")
                .font(.system(size: 80))
                .foregroundColor(.white.opacity(0.7))

            Text(NSLocalizedString("idle.pointAtShelf", comment: "Idle screen title"))
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)

            Text(NSLocalizedString("idle.takePhotoToSee", comment: "Idle screen subtitle"))
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            VStack(spacing: 12) {
                if cameraAvailable {
                    Button(action: onScanCamera) {
                        Label(NSLocalizedString("idle.scanShelf", comment: "Scan shelf button"), systemImage: "camera.fill")
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
                    Label(cameraAvailable ? NSLocalizedString("idle.choosePhoto", comment: "Choose photo button") : NSLocalizedString("idle.selectPhoto", comment: "Select photo button"), systemImage: "photo.on.rectangle")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Color.white.opacity(0.2))
                        .cornerRadius(12)
                }
                .accessibilityIdentifier("choosePhotoButton")
                .padding(.horizontal, 40)
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
        NSLocalizedString("processing.tip1", comment: "Tip: tap badge"),
        NSLocalizedString("processing.tip2", comment: "Tip: gold highlight"),
        NSLocalizedString("processing.tip3", comment: "Tip: review count"),
        NSLocalizedString("processing.tip4", comment: "Tip: wine count"),
    ]

    @State private var currentTipIndex = 0
    let timer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
                .tint(.white)
                .accessibilityIdentifier("processingSpinner")

            Text(NSLocalizedString("processing.analyzing", comment: "Processing status"))
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
                Button(NSLocalizedString("error.tryAgain", comment: "Retry button"), action: onRetry)
                    .buttonStyle(.bordered)
                    .tint(.white)
                    .accessibilityIdentifier("retryButton")

                Button(NSLocalizedString("error.startOver", comment: "Start over button"), action: onReset)
                    .buttonStyle(.borderedProminent)
                    .tint(.white)
                    .accessibilityIdentifier("startOverButton")
            }
        }
        .accessibilityIdentifier("errorView")
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

                Text(NSLocalizedString("about.title", comment: "About title"))
                    .font(.title2)
                    .fontWeight(.bold)

                Text(NSLocalizedString("about.description", comment: "About description"))
                    .font(.body)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                VStack(alignment: .leading, spacing: 8) {
                    Label(NSLocalizedString("about.winesCount", comment: "Wine count stat"), systemImage: "checkmark.circle.fill")
                        .foregroundColor(.secondary)
                    Label(NSLocalizedString("about.reviewsCount", comment: "Review count stat"), systemImage: "star.fill")
                        .foregroundColor(.secondary)
                }
                .font(.subheadline)

                Spacer()

                Text(NSLocalizedString("about.disclaimer", comment: "About disclaimer"))
                    .font(.caption)
                    .foregroundColor(.gray)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
            .padding(.top, 32)
            .padding(.horizontal)
            .navigationTitle(NSLocalizedString("about.heading", comment: "About navigation title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(NSLocalizedString("about.done", comment: "Done button")) { dismiss() }
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
