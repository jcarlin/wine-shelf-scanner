import SwiftUI

/// Main content view that manages the scan flow
struct ContentView: View {
    @StateObject private var viewModel: ScanViewModel
    @State private var showCamera = false
    @State private var showPhotoPicker = false
    @State private var capturedImage: UIImage?

    /// Whether we're running in UI test mode (bypass photo picker)
    private var isUITesting: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.environment["USE_MOCKS"] == "true"
        #else
        return false
        #endif
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

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                switch viewModel.state {
                case .idle:
                    IdleView(
                        onScanCamera: {
                            if isUITesting {
                                // Bypass camera, directly trigger scan with mock image
                                let mockImage = Self.createMockImage()
                                capturedImage = mockImage
                                viewModel.performScan(with: mockImage)
                            } else {
                                showCamera = true
                            }
                        },
                        onScanLibrary: {
                            if isUITesting {
                                // Bypass photo picker, directly trigger scan with mock image
                                let mockImage = Self.createMockImage()
                                capturedImage = mockImage
                                viewModel.performScan(with: mockImage)
                            } else {
                                showPhotoPicker = true
                            }
                        }
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
            .sheet(isPresented: $showCamera) {
                CameraView(image: $capturedImage, isPresented: $showCamera)
                    .ignoresSafeArea()
            }
            .sheet(isPresented: $showPhotoPicker) {
                PhotoPicker(image: $capturedImage, isPresented: $showPhotoPicker)
                    .ignoresSafeArea()
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

    @State private var cameraAvailable = UIImagePickerController.isSourceTypeAvailable(.camera)

    var body: some View {
        VStack(spacing: 24) {
            Image(systemName: "camera.viewfinder")
                .font(.system(size: 80))
                .foregroundColor(.white.opacity(0.7))

            Text(NSLocalizedString("idle.pointAtShelf", comment: "Idle screen title"))
                .font(.title2)
                .foregroundColor(.white)

            Text(NSLocalizedString("idle.takePhotoToSee", comment: "Idle screen subtitle"))
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.6))

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
        }
    }
}

struct ProcessingView: View {
    var body: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
                .tint(.white)
                .accessibilityIdentifier("processingSpinner")

            Text(NSLocalizedString("processing.analyzing", comment: "Processing status"))
                .font(.headline)
                .foregroundColor(.white)
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

#Preview {
    ContentView()
}
