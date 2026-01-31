import SwiftUI

/// Main content view that manages the scan flow
struct ContentView: View {
    @StateObject private var viewModel: ScanViewModel
    @State private var showCamera = false
    @State private var showPhotoPicker = false
    @State private var capturedImage: UIImage?

    init(viewModel: ScanViewModel? = nil) {
        _viewModel = StateObject(wrappedValue: viewModel ?? Self.createDefaultViewModel())
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
                        onScanCamera: { showCamera = true },
                        onScanLibrary: { showPhotoPicker = true }
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
                        }
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
            .navigationTitle("Wine Scanner")
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

            Text("Point at a wine shelf")
                .font(.title2)
                .foregroundColor(.white)

            Text("Take a photo to see ratings")
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.6))

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

            Text("Analyzing wines...")
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
                Button("Try Again", action: onRetry)
                    .buttonStyle(.bordered)
                    .tint(.white)
                    .accessibilityIdentifier("retryButton")

                Button("Start Over", action: onReset)
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
