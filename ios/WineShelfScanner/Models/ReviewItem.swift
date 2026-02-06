import Foundation

/// A single wine review from the backend
struct ReviewItem: Codable, Identifiable {
    let sourceName: String
    let reviewer: String?
    let rating: Double?
    let reviewText: String?
    let reviewDate: String?
    let vintage: String?

    var id: String { "\(sourceName)_\(reviewer ?? "")_\(reviewDate ?? "")" }

    enum CodingKeys: String, CodingKey {
        case sourceName = "source_name"
        case reviewer
        case rating
        case reviewText = "review_text"
        case reviewDate = "review_date"
        case vintage
    }
}

/// Response from GET /wines/{id}/reviews
struct WineReviewsResponse: Codable {
    let wineId: Int
    let wineName: String
    let totalReviews: Int
    let textReviews: Int
    let avgRating: Double?
    let reviews: [ReviewItem]

    enum CodingKeys: String, CodingKey {
        case wineId = "wine_id"
        case wineName = "wine_name"
        case totalReviews = "total_reviews"
        case textReviews = "text_reviews"
        case avgRating = "avg_rating"
        case reviews
    }
}
