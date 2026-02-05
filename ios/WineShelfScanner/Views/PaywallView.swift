import SwiftUI
import StoreKit

/// Professional paywall presented when the user exhausts free scans.
///
/// - Monthly: $4.99/month
/// - Annual: $29.99/year (50% savings, pre-selected)
/// - Dismiss returns to idle; scanning remains blocked until subscribed.
struct PaywallView: View {
    @ObservedObject var subscriptionManager: SubscriptionManager
    @Environment(\.dismiss) private var dismiss
    @State private var selectedPlan: PlanType = .annual
    @State private var isPurchasing = false

    enum PlanType {
        case monthly, annual
    }

    private let wineColor = Color(red: 0.45, green: 0.18, blue: 0.22)
    private let goldColor = Color(red: 1.0, green: 0.84, blue: 0.0)

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [Color.black, wineColor.opacity(0.3), Color.black],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 28) {
                        heroSection
                        planSelector
                        featuresList
                        ctaSection
                        footerSection
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 16)
                    .padding(.bottom, 40)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title3)
                            .foregroundStyle(.white.opacity(0.5))
                    }
                    .accessibilityIdentifier("paywallCloseButton")
                }
            }
        }
        .preferredColorScheme(.dark)
        .task {
            await subscriptionManager.loadProducts()
        }
    }

    // MARK: - Hero

    private var heroSection: some View {
        VStack(spacing: 12) {
            Image(systemName: "wineglass.fill")
                .font(.system(size: 56))
                .foregroundStyle(
                    LinearGradient(
                        colors: [goldColor, goldColor.opacity(0.7)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .shadow(color: goldColor.opacity(0.3), radius: 12)

            Text("Unlimited Instant Ratings")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)

            Text("Never second-guess a bottle again.\nScan any shelf and see the best picks in seconds.")
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
                .lineSpacing(2)
        }
        .padding(.top, 8)
    }

    // MARK: - Plan Selector

    private var planSelector: some View {
        HStack(spacing: 12) {
            planCard(
                type: .monthly,
                title: "Monthly",
                price: monthlyPriceText,
                detail: "per month",
                badge: nil
            )

            planCard(
                type: .annual,
                title: "Annual",
                price: annualPriceText,
                detail: annualDetailText,
                badge: "SAVE 50%"
            )
        }
    }

    private func planCard(
        type: PlanType,
        title: String,
        price: String,
        detail: String,
        badge: String?
    ) -> some View {
        let isSelected = selectedPlan == type

        return Button {
            withAnimation(.easeInOut(duration: 0.2)) {
                selectedPlan = type
            }
        } label: {
            VStack(spacing: 8) {
                if let badge = badge {
                    Text(badge)
                        .font(.caption2)
                        .fontWeight(.heavy)
                        .foregroundColor(.black)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(goldColor)
                        .cornerRadius(4)
                } else {
                    Text(" ")
                        .font(.caption2)
                        .fontWeight(.heavy)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .opacity(0)
                }

                Text(title)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundColor(isSelected ? .white : .white.opacity(0.6))

                Text(price)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(isSelected ? .white : .white.opacity(0.6))

                Text(detail)
                    .font(.caption)
                    .foregroundColor(isSelected ? .white.opacity(0.6) : .white.opacity(0.4))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 16)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isSelected ? wineColor.opacity(0.4) : Color.white.opacity(0.05))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(
                        isSelected ? goldColor.opacity(0.6) : Color.white.opacity(0.1),
                        lineWidth: isSelected ? 2 : 1
                    )
            )
        }
        .accessibilityIdentifier(type == .monthly ? "monthlyPlanButton" : "annualPlanButton")
    }

    // MARK: - Features

    private var featuresList: some View {
        VStack(alignment: .leading, spacing: 14) {
            featureRow(icon: "camera.viewfinder", text: "Unlimited shelf scans")
            featureRow(icon: "star.fill", text: "Ratings from 21 million reviews")
            featureRow(icon: "wineglass", text: "181,000+ wines covered")
            featureRow(icon: "bolt.fill", text: "Instant bottle identification")
        }
        .padding(.horizontal, 4)
    }

    private func featureRow(icon: String, text: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.body)
                .foregroundColor(goldColor)
                .frame(width: 24)

            Text(text)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.9))
        }
    }

    // MARK: - CTA

    private var ctaSection: some View {
        VStack(spacing: 8) {
            Button {
                Task {
                    isPurchasing = true
                    defer { isPurchasing = false }

                    let product: Product? = selectedPlan == .annual
                        ? subscriptionManager.annualProduct
                        : subscriptionManager.monthlyProduct

                    guard let product = product else { return }
                    let success = await subscriptionManager.purchase(product)
                    if success {
                        dismiss()
                    }
                }
            } label: {
                Group {
                    if isPurchasing || subscriptionManager.isLoading {
                        ProgressView()
                            .tint(.black)
                    } else {
                        Text("Continue")
                            .fontWeight(.semibold)
                    }
                }
                .foregroundColor(.black)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(
                    LinearGradient(
                        colors: [goldColor, goldColor.opacity(0.85)],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .cornerRadius(14)
            }
            .disabled(isPurchasing || subscriptionManager.isLoading)
            .accessibilityIdentifier("subscribeButton")

            if let error = subscriptionManager.purchaseError {
                Text(error)
                    .font(.caption)
                    .foregroundColor(.red.opacity(0.8))
                    .multilineTextAlignment(.center)
            }
        }
    }

    // MARK: - Footer

    private var footerSection: some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    await subscriptionManager.restorePurchases()
                    if subscriptionManager.isSubscribed {
                        dismiss()
                    }
                }
            } label: {
                Text("Restore Purchases")
                    .font(.subheadline)
                    .foregroundColor(.white.opacity(0.5))
            }
            .accessibilityIdentifier("restorePurchasesButton")

            Text("Payment charged to your Apple ID. Auto-renews unless cancelled at least 24 hours before the current period ends. Manage anytime in Settings.")
                .font(.caption2)
                .foregroundColor(.white.opacity(0.3))
                .multilineTextAlignment(.center)
                .lineSpacing(2)
        }
    }

    // MARK: - Pricing Helpers

    private var monthlyPriceText: String {
        subscriptionManager.monthlyProduct?.displayPrice ?? "$4.99"
    }

    private var annualPriceText: String {
        subscriptionManager.annualProduct?.displayPrice ?? "$29.99"
    }

    private var annualDetailText: String {
        if let annual = subscriptionManager.annualProduct {
            let monthlyEquivalent = annual.price / 12
            let formatter = NumberFormatter()
            formatter.numberStyle = .currency
            formatter.locale = annual.priceFormatStyle.locale
            if let formatted = formatter.string(from: monthlyEquivalent as NSDecimalNumber) {
                return "just \(formatted)/mo"
            }
        }
        return "just $2.50/mo"
    }
}

#Preview {
    PaywallView(subscriptionManager: SubscriptionManager.shared)
}
