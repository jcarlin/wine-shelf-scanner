# iOS Parity Audit (vs Next.js)

**Date:** February 6, 2026
**Direction:** What does Next.js have that iOS is missing?

---

## Summary

The iOS and Next.js frontends share the same core architecture (API contract, overlay math, confidence UX, feature flags), but recent Next.js development has introduced several features and polish improvements that iOS lacks. This audit identifies **7 gaps** where iOS should catch up, **2 reverse gaps** where iOS is ahead, and **3 platform-specific differences** that are intentional.

### Priority Legend

| Priority | Meaning |
|----------|---------|
| **P0** | Impacts core UX or causes user-facing failures |
| **P1** | Notable quality/polish gap |
| **P2** | Nice-to-have, low urgency |

---

## Parity Status At A Glance

| Feature Area | iOS | Next.js | Parity? |
|---|---|---|---|
| Scan endpoint (POST /scan) | Yes | Yes | ✅ |
| Confidence-based opacity | Yes | Yes | ✅ |
| Top-3 emphasis (glow, sizing) | Yes | Yes | ✅ |
| Rating badges | Yes | Yes | ✅ |
| Detail sheet / modal | Yes | Yes | ✅ |
| Fallback list | Yes | Yes | ✅ |
| Partial detection toast | Yes | Yes | ✅ |
| Bug report (POST /report) | Yes | Yes | ✅ |
| Feature flags (12 iOS / 10 Next.js) | Yes | Yes | ✅ |
| Wine memory (local like/dislike) | Yes | Yes | ✅ |
| Offline scan cache | Yes | Yes | ✅ |
| Corner brackets (top-3) | Yes | Yes | ✅ |
| Share results | Yes | Yes | ✅ |
| Debug tray | Yes | Yes | ✅ |
| i18n (10 languages) | Yes | Yes | ✅ |
| About sheet (DB stats) | Yes | Yes | ✅ |
| Visual emphasis (opacity boost/dim) | Yes | Yes | ✅ |
| Safe pick badge | Yes | Yes | ✅ |
| Trust signals | Yes | Yes | ✅ |
| Food pairings | Yes | Yes | ✅ |
| Shelf ranking | Yes | Yes | ✅ |
| **Server warmup handling** | **No** | Yes | ❌ P0 |
| **Wine reviews fetching** | **No** | Yes | ❌ P1 |
| **Scanning overlay (image preview)** | **No** | Yes | ❌ P1 |
| **Processing tips count** | 4 | 8 | ⚠️ P2 |
| **wine_id in WineResult model** | **No** | Yes | ❌ P1 |
| **Confidence opacity values** | Spec-exact | Slightly higher | ⚠️ P2 |
| **Feedback to backend** | Yes | **No** | 🔄 iOS ahead |
| **Background processing** | Yes | **No** | 🔄 iOS ahead |
| **Subscription/paywall** | Yes | **No** | 🔄 iOS ahead |

---

## iOS Gaps (Next.js has it, iOS doesn't)

### 1. Server Warmup / Cold Start Handling — P0

**Impact:** When Cloud Run has 0 min instances, cold starts take 15-30+ seconds. iOS users get a timeout error with no explanation. Next.js users see a friendly warmup screen.

**Next.js implementation:**
- `useServerHealth` hook polls `GET /health` on mount
- `ServerWarmupOverlay` component shows during cold start
- Up to 30 retries (~5 min) with rotating tips (30 warmup tips)
- States: `checking` → `warming_up` → `ready` / `unavailable`
- Confirmation checks (2 extra health pings after first success)

**iOS has:** Nothing. `ScanService` sends the scan request directly. If Cloud Run is cold, the 45-second timeout may expire and the user sees a generic error.

**Recommendation:** Add a `ServerHealthService` that checks `GET /health` before the first scan. Show a warmup overlay (similar to `ProcessingView` but with warmup-specific messaging). Gate the scan button until the server is ready.

**Files to create/modify:**
- New: `ios/WineShelfScanner/Services/ServerHealthService.swift`
- New: `ios/WineShelfScanner/Views/ServerWarmupView.swift`
- Modify: `ContentView.swift` — add health check on launch, show warmup overlay
- Add: Localization keys for `warmup.*` (already exist in some .strings files from Next.js parity)

---

### 2. Wine Reviews Fetching — P1

**Impact:** Next.js shows richer review data in the detail modal by fetching from `GET /wines/{id}/reviews`. iOS only displays the `reviewSnippets` and `reviewCount` from the scan response (static, limited).

**Next.js implementation:**
- `useWineReviews` hook fires parallel requests for all wines with `wine_id`
- `fetchWineReviews(id, limit=5, textOnly=true)` via API client
- Reviews populate incrementally as responses arrive
- `WineDetailModal` displays fetched reviews with source attribution, dates, and vintage

**iOS has:**
- `reviewSnippets: [String]?` and `reviewCount: Int?` in `WineResult` model
- `WineDetailSheet` displays these static snippets
- No `wine_id` field in the model
- No API call to `/wines/{id}/reviews`

**Recommendation:**
1. Add `wineId: Int?` (coded as `wine_id`) to `WineResult` model
2. Add `fetchWineReviews(id:)` to `ScanService`
3. Create a `ReviewItem` model matching the backend response
4. Prefetch reviews in `ScanViewModel` after scan completes
5. Update `WineDetailSheet` to prefer fetched reviews over static snippets

**Files to create/modify:**
- Modify: `ScanResponse.swift` — add `wineId` field
- New: `ios/WineShelfScanner/Models/ReviewItem.swift`
- Modify: `ScanService.swift` — add `fetchWineReviews()` method
- Modify: `ScanViewModel.swift` — prefetch reviews after scan
- Modify: `WineDetailSheet.swift` — display fetched reviews

---

### 3. Scanning Overlay (Image Preview During Processing) — P1

**Impact:** Next.js shows the user's actual photo with an animated gold scanner line sweeping across it during processing. This provides visual confirmation that the right image was captured and creates a more engaging wait. iOS shows a generic spinner.

**Next.js implementation:**
- Two-state pattern: `ScanningOverlay` (when image available) or `ProcessingSpinner` (fallback)
- `ScanningOverlay` renders the uploaded image with a CSS-animated gold line + glow effect
- Tips rotate below the image

**iOS has:**
- `ProcessingView` — a `ProgressView()` spinner with "Analyzing..." text and 4 rotating tips
- The captured `UIImage` is available in `ScanViewModel` but not shown during processing

**Recommendation:** Create a `ScanningOverlayView` that displays the captured image with an animated scanning line (using a `LinearGradient` + repeating animation). Fall back to current `ProcessingView` if the image is unavailable.

**Files to create/modify:**
- New: `ios/WineShelfScanner/Views/ScanningOverlayView.swift`
- Modify: `ContentView.swift` — use `ScanningOverlayView` when image is available during `.processing` state

---

### 4. Processing Tips Count — P2

**Impact:** Minor polish gap. Next.js shows 8 rotating tips during scanning, iOS shows 4. More tips reduce repetition during longer scans.

**Next.js tips (8):**
1. Wine ratings are aggregated from millions of reviews
2. We analyze label text to identify each bottle
3. Higher-rated wines are highlighted for quick selection
4. Tap any rating badge for detailed wine information
5. Our database covers 181,000+ wines worldwide
6. Ratings combine scores from major wine platforms
7. Works best with clear, well-lit photos of wine shelves
8. Confidence scores show how certain each match is

**iOS tips (4):**
1. processing.tip1–tip4 (varies by localization)

**Recommendation:** Add 4 more tips to iOS `ProcessingView` to match Next.js. Add corresponding localization keys to all 10 language files.

**Files to modify:**
- `ContentView.swift` (ProcessingView struct) — add tips 5-8
- All 10 `.lproj/Localizable.strings` files — add `processing.tip5` through `processing.tip8`

---

### 5. wine_id Field in WineResult — P1

**Impact:** Blocks review fetching (Gap #2) and potentially other future features that require linking to the wines database.

**Next.js type:** `wine_id?: number` in `WineResult`
**iOS model:** No `wineId` field

This is a prerequisite for Gap #2 above — listed separately because it's a model change.

**Files to modify:**
- `ScanResponse.swift` — add `wineId: Int?` with `CodingKey` mapping to `wine_id`

---

### 6. Confidence Opacity Mismatch — P2

**Impact:** Minor visual inconsistency. The confidence-to-opacity mapping differs slightly between platforms.

| Confidence | CLAUDE.md Spec | iOS | Next.js |
|---|---|---|---|
| >= 0.85 | 1.0 | 1.0 | 1.0 |
| 0.65–0.85 | 0.75 | 0.75 | 0.9 |
| 0.45–0.65 | 0.5 | 0.5 | 0.8 |
| < 0.45 | Hidden | 0.0 | 0.0 |

iOS follows the CLAUDE.md spec exactly. Next.js uses higher opacity values (0.9 and 0.8 instead of 0.75 and 0.5). This makes lower-confidence wines more visible on web.

**Recommendation:** Decide which values are correct and align both platforms. If the higher values tested better on web, update both CLAUDE.md and iOS. If the spec values are intentional, fix Next.js.

**Files potentially affected:**
- `OverlayMath.swift` — `opacityForConfidence()` function
- `nextjs/lib/overlay-math.ts` — `confidenceOpacity()` function
- `CLAUDE.md` — update spec if changing

---

### 7. HEIC Preview Endpoint — P2

**Impact:** None for iOS (native HEIC support). Noted for completeness.

Next.js uses `POST /preview` to convert HEIC images server-side for browsers that can't display them. iOS handles HEIC natively — no action needed.

---

## Reverse Gaps (iOS has it, Next.js doesn't)

### A. Feedback Submission to Backend — P1

**iOS:** Calls `POST /feedback` with `isCorrect`, `correctedName`, `ocrText`, `deviceId`. This allows the backend to accumulate wine match corrections and improve accuracy over time.

**Next.js:** Only stores feedback locally via `useWineMemory` hook (localStorage). Thumbs up/down feedback never reaches the server.

**Recommendation:** Add a `submitFeedback()` function to the Next.js API client and wire it into `WineDetailModal` alongside the existing wine memory save.

---

### B. Background Scan Processing — iOS-specific

**iOS:** `BackgroundScanManager` uses `URLSession` background uploads so scans continue if the app is suspended. Includes local notifications on completion.

**Next.js:** Not applicable (browser limitation). No action needed.

---

### C. Subscription / Paywall — iOS-specific (deferred)

**iOS:** Full StoreKit 2 integration with `PaywallView`, `SubscriptionManager`, `ScanCounter`. Feature-flagged off by default.

**Next.js:** Not implemented. Per ROADMAP.md, paywall is deferred (post-MVP). No action needed now.

---

## Platform-Specific Differences (Intentional)

| Feature | iOS | Next.js | Notes |
|---|---|---|---|
| Camera capture | UIImagePickerController | `<input capture="environment">` | Platform APIs differ |
| Drag-and-drop upload | N/A | Yes | Web-only UX pattern |
| HEIC conversion | Native | heic2any + backend fallback | iOS handles natively |
| Background processing | URLSession | N/A | Mobile-only capability |
| Local notifications | UNUserNotificationCenter | N/A | Mobile-only |
| Network quality adaptation | NWPathMonitor (0.5/0.8 quality) | Fixed 0.8 quality | iOS can detect metered connections |
| Star rating display | Visual stars (filled/half/empty) | Numeric + single star icon | Stylistic choice |

---

## Recommended Implementation Order

| Priority | Gap | Effort | Impact |
|---|---|---|---|
| 1 | Server warmup handling (P0) | Medium | Prevents timeout errors on cold starts |
| 2 | wine_id model field (P1) | Small | Prerequisite for review fetching |
| 3 | Wine reviews fetching (P1) | Medium | Richer detail sheet content |
| 4 | Scanning overlay (P1) | Medium | Better processing UX |
| 5 | Feedback to backend (P1, reverse) | Small | Improve recognition accuracy over time |
| 6 | Processing tips (P2) | Small | Minor polish |
| 7 | Confidence opacity alignment (P2) | Small | Visual consistency |
