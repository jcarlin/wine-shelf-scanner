import StoreKit

/// Manages StoreKit 2 subscriptions for Wine Shelf Scanner.
///
/// Product IDs must be configured in App Store Connect:
/// - `com.wineshelfscanner.monthly` — $4.99/month
/// - `com.wineshelfscanner.annual` — $29.99/year
///
/// For local testing, create a StoreKit Configuration file in Xcode:
/// File > New > StoreKit Configuration File
@MainActor
class SubscriptionManager: ObservableObject {
    static let shared = SubscriptionManager()

    static let monthlyProductID = "com.wineshelfscanner.monthly"
    static let annualProductID = "com.wineshelfscanner.annual"

    @Published private(set) var isSubscribed = false
    @Published private(set) var products: [Product] = []
    @Published private(set) var purchaseError: String?
    @Published private(set) var isLoading = false

    private let productIDs: Set<String> = [
        monthlyProductID,
        annualProductID,
    ]

    private var transactionListener: Task<Void, Never>?

    init() {
        transactionListener = listenForTransactions()
        Task { await checkEntitlements() }
    }

    deinit {
        transactionListener?.cancel()
    }

    // MARK: - Products

    /// Load available products from the App Store.
    func loadProducts() async {
        do {
            let storeProducts = try await Product.products(for: productIDs)
            products = storeProducts.sorted { $0.price < $1.price }
        } catch {
            // Products remain empty — paywall shows fallback pricing text.
        }
    }

    var monthlyProduct: Product? {
        products.first { $0.id == Self.monthlyProductID }
    }

    var annualProduct: Product? {
        products.first { $0.id == Self.annualProductID }
    }

    // MARK: - Purchase

    /// Purchase a subscription. Returns `true` on success.
    func purchase(_ product: Product) async -> Bool {
        isLoading = true
        purchaseError = nil
        defer { isLoading = false }

        do {
            let result = try await product.purchase()
            switch result {
            case .success(let verification):
                let transaction = try checkVerified(verification)
                await transaction.finish()
                await checkEntitlements()
                return true
            case .userCancelled:
                return false
            case .pending:
                return false
            @unknown default:
                return false
            }
        } catch {
            purchaseError = "Purchase could not be completed. Please try again."
            return false
        }
    }

    // MARK: - Restore

    /// Restore previous purchases via App Store sync.
    func restorePurchases() async {
        isLoading = true
        purchaseError = nil
        defer { isLoading = false }
        do {
            try await AppStore.sync()
        } catch {
            purchaseError = "Could not restore purchases. Please try again."
        }
        await checkEntitlements()
    }

    // MARK: - Entitlements

    /// Check whether the user has an active subscription entitlement.
    func checkEntitlements() async {
        var found = false
        for await result in Transaction.currentEntitlements {
            if case .verified(let transaction) = result,
               productIDs.contains(transaction.productID) {
                found = true
                break
            }
        }
        isSubscribed = found
    }

    // MARK: - Verification

    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T {
        switch result {
        case .verified(let value):
            return value
        case .unverified(_, let error):
            throw error
        }
    }

    // MARK: - Transaction Listener

    /// Listen for transaction updates (renewals, revocations, etc.)
    private func listenForTransactions() -> Task<Void, Never> {
        Task.detached { [weak self] in
            for await result in Transaction.updates {
                if case .verified(let transaction) = result {
                    await transaction.finish()
                    await self?.checkEntitlements()
                }
            }
        }
    }
}
