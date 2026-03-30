import SwiftUI

/// Shows the captured image with an animated scanning line during processing.
///
/// Mirrors the Next.js `ScanningOverlay` component. Displays the user's photo
/// with a gold scanner line sweeping vertically, providing visual confirmation
/// that the correct image was captured.
struct ScanningOverlayView: View {
    let image: UIImage

    private let tips: [String] = (1...8).map { index in
        NSLocalizedString("processing.tip\(index)", comment: "Processing tip \(index)")
    }

    @State private var currentTipIndex = 0
    @State private var scanLinePosition: CGFloat = 0
    let tipTimer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(spacing: 0) {
            // Image with scanner line
            GeometryReader { geo in
                ZStack {
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipped()

                    // Animated scanner line
                    scannerLine(in: geo.size)
                }
            }
            .cornerRadius(12)
            .padding(.horizontal, 16)

            // Status text
            Text(NSLocalizedString("processing.analyzing", comment: "Processing status"))
                .font(.headline)
                .foregroundColor(.white)
                .padding(.top, 16)

            // Rotating tip
            Text(tips[currentTipIndex])
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.5))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
                .padding(.top, 8)
                .id(currentTipIndex)
                .transition(.opacity)
                .animation(.easeInOut(duration: 0.5), value: currentTipIndex)
        }
        .padding(.vertical, 16)
        .onReceive(tipTimer) { _ in
            currentTipIndex = (currentTipIndex + 1) % tips.count
        }
        .onAppear {
            withAnimation(.linear(duration: 2.5).repeatForever(autoreverses: true)) {
                scanLinePosition = 1
            }
        }
    }

    private func scannerLine(in size: CGSize) -> some View {
        // Calculate image bounds for proper positioning
        let imageBounds = OverlayMath.getImageBounds(imageSize: image.size, containerSize: size)

        return VStack(spacing: 0) {
            // Glow above line
            LinearGradient(
                colors: [.clear, Color.yellow.opacity(0.15), .clear],
                startPoint: .top,
                endPoint: .bottom
            )
            .frame(height: 32)

            // Core scanner line
            Rectangle()
                .fill(Color.yellow)
                .frame(height: 2)
                .shadow(color: .yellow, radius: 10)
                .shadow(color: .yellow, radius: 20)
        }
        .frame(width: imageBounds.width)
        .offset(
            x: imageBounds.origin.x + imageBounds.width / 2 - size.width / 2,
            y: imageBounds.origin.y + scanLinePosition * imageBounds.height - size.height / 2
        )
    }
}

#Preview {
    ZStack {
        Color.black.ignoresSafeArea()
        ScanningOverlayView(image: UIImage(systemName: "photo")!)
    }
}
