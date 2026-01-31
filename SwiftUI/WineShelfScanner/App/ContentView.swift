import SwiftUI

/// Main content view that manages the scan flow
struct ContentView: View {
    @StateObject private var viewModel = ScanViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                switch viewModel.state {
                case .idle:
                    IdleView(onScan: viewModel.startScan)

                case .processing:
                    ProcessingView()

                case .results(let response, let image):
                    ResultsView(
                        response: response,
                        image: image,
                        onNewScan: viewModel.reset
                    )

                case .error(let message):
                    ErrorView(
                        message: message,
                        onRetry: viewModel.startScan,
                        onReset: viewModel.reset
                    )
                }
            }
            .navigationTitle("Wine Scanner")
            .navigationBarTitleDisplayMode(.inline)
            .preferredColorScheme(.dark)
        }
    }
}

// MARK: - Supporting Views

struct IdleView: View {
    let onScan: () -> Void

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

            Button(action: onScan) {
                Label("Scan Shelf", systemImage: "camera.fill")
                    .font(.headline)
                    .foregroundColor(.black)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 16)
                    .background(Color.white)
                    .cornerRadius(12)
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

            HStack(spacing: 16) {
                Button("Try Again", action: onRetry)
                    .buttonStyle(.bordered)
                    .tint(.white)

                Button("Start Over", action: onReset)
                    .buttonStyle(.borderedProminent)
                    .tint(.white)
            }
        }
    }
}

#Preview {
    ContentView()
}
