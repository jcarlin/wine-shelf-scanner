import SwiftUI

/// Overlay shown while the backend is cold-starting.
///
/// Mirrors the Next.js `ServerWarmupOverlay` component. Shows a spinning wine
/// icon with rotating tips while the Cloud Run instance warms up.
struct ServerWarmupView: View {
    let state: ServerHealthService.State
    let onRetry: () -> Void

    private let tips: [String] = (1...8).map { index in
        NSLocalizedString("warmup.tip\(index)", comment: "Warmup tip \(index)")
    }

    @State private var currentTipIndex = 0
    let timer = Timer.publish(every: 4, on: .main, in: .common).autoconnect()

    // Wine burgundy color matching the app theme
    private let wineColor = Color(red: 0.45, green: 0.18, blue: 0.22)

    var body: some View {
        ZStack {
            Color(red: 0.10, green: 0.10, blue: 0.18)
                .ignoresSafeArea()

            switch state {
            case .checking:
                checkingView
            case .warmingUp:
                warmingUpView
            case .unavailable(let message):
                unavailableView(message: message)
            case .ready:
                EmptyView()
            }
        }
    }

    private var checkingView: some View {
        VStack(spacing: 16) {
            spinnerIcon
            Text(NSLocalizedString("warmup.checking", comment: "Checking server status"))
                .font(.subheadline)
                .foregroundColor(.gray)
        }
    }

    private var warmingUpView: some View {
        VStack(spacing: 16) {
            spinnerIcon

            Text(NSLocalizedString("warmup.title", comment: "Warming up title"))
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(.white)

            Text(NSLocalizedString("warmup.message", comment: "Warming up message"))
                .font(.subheadline)
                .foregroundColor(.gray)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            // Bouncing dots
            HStack(spacing: 8) {
                ForEach(0..<3) { i in
                    Circle()
                        .fill(Color.yellow)
                        .frame(width: 8, height: 8)
                        .offset(y: bouncingOffset(index: i))
                        .animation(
                            .easeInOut(duration: 0.5)
                                .repeatForever(autoreverses: true)
                                .delay(Double(i) * 0.15),
                            value: true
                        )
                }
            }
            .padding(.vertical, 8)

            // Rotating tip
            Text(tips[currentTipIndex])
                .font(.caption)
                .italic()
                .foregroundColor(.gray.opacity(0.7))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
                .id(currentTipIndex)
                .transition(.opacity)
                .animation(.easeInOut(duration: 0.5), value: currentTipIndex)
        }
        .onReceive(timer) { _ in
            currentTipIndex = (currentTipIndex + 1) % tips.count
        }
    }

    private func unavailableView(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "wineglass.fill")
                .font(.system(size: 48))
                .foregroundColor(.white)
                .padding(24)
                .background(wineColor.opacity(0.5))
                .clipShape(Circle())

            Text(NSLocalizedString("warmup.unavailableTitle", comment: "Server unavailable title"))
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(.white)

            Text(message)
                .font(.subheadline)
                .foregroundColor(.gray)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Button(action: onRetry) {
                HStack(spacing: 8) {
                    Image(systemName: "arrow.clockwise")
                        .font(.subheadline)
                    Text(NSLocalizedString("warmup.retry", comment: "Retry button"))
                        .font(.headline)
                }
                .foregroundColor(.black)
                .padding(.horizontal, 32)
                .padding(.vertical, 14)
                .background(Color.white)
                .cornerRadius(12)
            }
            .padding(.top, 8)
        }
    }

    private var spinnerIcon: some View {
        ZStack {
            Circle()
                .fill(wineColor)
                .frame(width: 96, height: 96)

            Image(systemName: "wineglass.fill")
                .font(.system(size: 48))
                .foregroundColor(.white)

            Circle()
                .stroke(Color.clear, lineWidth: 4)
                .overlay(
                    Circle()
                        .trim(from: 0, to: 0.3)
                        .stroke(Color.yellow, lineWidth: 4)
                        .rotationEffect(.degrees(-90))
                )
                .frame(width: 96, height: 96)
                .rotationEffect(.degrees(360))
                .animation(.linear(duration: 1.5).repeatForever(autoreverses: false), value: true)
        }
        .padding(.bottom, 16)
    }

    private func bouncingOffset(index: Int) -> CGFloat {
        // Simple static offset; animation handles the bouncing
        -4
    }
}

#Preview("Checking") {
    ServerWarmupView(state: .checking, onRetry: {})
}

#Preview("Warming Up") {
    ServerWarmupView(state: .warmingUp(attempt: 3), onRetry: {})
}

#Preview("Unavailable") {
    ServerWarmupView(
        state: .unavailable(message: "Server is taking too long to start. Please try again later."),
        onRetry: {}
    )
}
