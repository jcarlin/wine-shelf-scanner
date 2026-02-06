import SwiftUI

/// Browse and view previously cached scan results
struct CachedScansView: View {
    @ObservedObject var viewModel: ScanViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var cachedEntries: [ScanCacheService.CachedScan] = []

    private let cache = ScanCacheService.shared

    private static let relativeDateFormatter: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .short
        return f
    }()

    var body: some View {
        NavigationStack {
            Group {
                if cachedEntries.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "clock.arrow.circlepath")
                            .font(.system(size: 48))
                            .foregroundColor(.gray)
                        Text("No recent scans")
                            .font(.headline)
                            .foregroundColor(.secondary)
                        Text("Your scan results will appear here for offline access.")
                            .font(.subheadline)
                            .foregroundColor(.gray)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 32)
                    }
                } else {
                    List {
                        ForEach(cachedEntries) { entry in
                            CachedScanRow(entry: entry)
                                .contentShape(Rectangle())
                                .onTapGesture {
                                    viewModel.showCachedScan(entry)
                                    dismiss()
                                }
                        }
                        .onDelete { indexSet in
                            for index in indexSet {
                                cache.delete(at: index)
                            }
                            cachedEntries = cache.entries()
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Recent Scans")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if !cachedEntries.isEmpty {
                        Button("Clear All") {
                            cache.clearAll()
                            cachedEntries = []
                        }
                        .foregroundColor(.red)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear {
                cachedEntries = cache.entries()
            }
        }
        .accessibilityIdentifier("cachedScansView")
    }
}

/// Row displaying a single cached scan entry
struct CachedScanRow: View {
    let entry: ScanCacheService.CachedScan

    @State private var thumbnail: UIImage?

    private var topWineName: String {
        entry.response.topRatedResults.first?.wineName ?? "Scan"
    }

    private var topRating: String {
        guard let rating = entry.response.topRatedResults.first?.rating else { return "" }
        return String(format: "%.1f", rating)
    }

    private var wineCount: Int {
        entry.response.results.count
    }

    private var relativeTime: String {
        CachedScansView.relativeDateFormatter.localizedString(
            for: entry.timestamp, relativeTo: Date()
        )
    }

    var body: some View {
        HStack(spacing: 12) {
            // Thumbnail
            Group {
                if let thumbnail = thumbnail {
                    Image(uiImage: thumbnail)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                } else {
                    Image(systemName: "photo")
                        .foregroundColor(.gray)
                }
            }
            .frame(width: 50, height: 50)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.gray.opacity(0.2))
            )

            // Details
            VStack(alignment: .leading, spacing: 4) {
                Text(topWineName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .lineLimit(1)

                HStack(spacing: 8) {
                    if !topRating.isEmpty {
                        HStack(spacing: 2) {
                            Image(systemName: "star.fill")
                                .font(.system(size: 10))
                                .foregroundColor(.yellow)
                            Text(topRating)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    Text("\(wineCount) wine\(wineCount != 1 ? "s" : "")")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            // Timestamp
            Text(relativeTime)
                .font(.caption2)
                .foregroundColor(.gray)

            Image(systemName: "chevron.right")
                .font(.caption2)
                .foregroundColor(.gray)
        }
        .padding(.vertical, 4)
        .onAppear {
            thumbnail = ScanCacheService.shared.loadThumbnail(for: entry)
        }
    }
}
