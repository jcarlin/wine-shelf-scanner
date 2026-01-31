# Wine Shelf Scanner - Development Plan

## Project Overview

**Goal:** Photo-based iOS app that overlays star ratings directly on wine bottles in a shelf photo.

**Success Metric:** User takes one photo → sees ratings → chooses confidently in <10 seconds.

**Tech Stack:**
- iOS: SwiftUI (iOS 16+), native camera
- Backend: FastAPI (Python), Google Cloud Vision API
- Hosting: Google Cloud Run (recommended)

---

## Phase Structure

| Phase | Name | Duration | Parallel Work |
|-------|------|----------|---------------|
| **0** | Prerequisites & Setup | 1-2 days | - |
| **1** | Foundation (Mock API + iOS Scaffold) | 3-4 days | Backend + iOS parallel |
| **2** | Vision Integration + Static Overlays | 4-5 days | Backend + iOS parallel |
| **3** | OCR Pipeline + Interaction Layer | 4-5 days | Backend + iOS parallel |
| **4** | Full Integration + Camera | 3-4 days | Integration testing |
| **5** | Polish + TestFlight | 3-4 days | Beta testing |
| **6** | App Store Submission | 3-7 days | Review process |

**Total: 5-7 weeks to App Store**

---

## Phase 0: Prerequisites & Setup

### Required Accounts & Credentials

| Item | Purpose | Action |
|------|---------|--------|
| Apple Developer Account | TestFlight + App Store | $99/year enrollment |
| Google Cloud Account | Vision API | Create project, enable billing |
| Google Vision API | OCR + object detection | Enable API, create service account |
| Anthropic API Key | (Optional) LLM normalization | For enhanced OCR cleanup |

### Development Environment

- [ ] Xcode 15+ installed
- [ ] Python 3.11+ installed
- [ ] Google Cloud CLI (`gcloud`) installed
- [ ] Create GCP project: `wine-shelf-scanner`
- [ ] Enable Vision API in GCP console
- [ ] Create service account with Vision API access
- [ ] Download credentials JSON

### Test Image Collection

Collect 20-30 wine shelf photos:
- Standard shelves (5-10 bottles)
- Dense shelves (15+ bottles)
- Partial occlusion
- Varied lighting
- Angled shots
- Non-wine shelves (failure cases)

### Gate 0 Criteria
- [ ] Apple Developer account active
- [ ] GCP project created with Vision API enabled
- [ ] Service account credentials downloaded
- [ ] At least 10 test images collected
- [ ] Development environment ready

---

## Phase 1: Foundation

### Backend (Days 1-3)

**Deliverables:**
1. FastAPI project structure
2. Mock `/scan` endpoint returning hardcoded JSON
3. Pydantic models matching API contract exactly
4. Multiple mock response fixtures

**Directory Structure:**
```
backend/
├── main.py
├── requirements.txt
├── .env.example
├── app/
│   ├── routes/scan.py
│   ├── models/response.py
│   └── mocks/fixtures.py
└── tests/
```

**API Contract (immutable):**
```json
{
  "image_id": "string",
  "results": [{
    "wine_name": "string",
    "rating": 4.6,
    "confidence": 0.92,
    "bbox": { "x": 0.25, "y": 0.40, "width": 0.10, "height": 0.30 }
  }],
  "fallback_list": [{ "wine_name": "string", "rating": 4.3 }]
}
```

**Mock Fixtures Required:**
- `full_shelf.json` - 8 bottles, varied confidence
- `partial_detection.json` - 3 detected, 5 in fallback
- `low_confidence.json` - All bottles <0.65 confidence
- `empty_results.json` - No detection, fallback only

### iOS (Days 1-3)

**Deliverables:**
1. Xcode project (`WineShelfScanner.xcodeproj`)
2. Swift models matching API contract
3. `MockScanService` using JSON fixtures
4. Integration of existing `OverlayMath.swift`
5. Test images in Assets

**Key Files:**
```
ios/
├── WineShelfScanner.xcodeproj
├── WineShelfScanner/
│   ├── App/WineShelfScannerApp.swift
│   ├── Models/ScanResponse.swift
│   ├── Services/ScanService.swift
│   ├── Services/MockScanService.swift
│   ├── Utils/OverlayMath.swift (existing)
│   └── Resources/MockData/
└── WineShelfScannerTests/
```

### Gate 1 Criteria

**Backend:**
- [ ] `uvicorn main:app --reload` starts without errors
- [ ] `POST /scan` accepts image, returns valid JSON
- [ ] Response matches API contract exactly (Pydantic validation)
- [ ] All mock fixtures return different scenarios

**iOS:**
- [ ] Project compiles and runs in simulator
- [ ] Models decode all JSON fixtures correctly
- [ ] MockScanService returns expected data
- [ ] Unit tests pass for OverlayMath

---

## Phase 2: Vision Integration + Static Overlays

### Backend (Days 4-7)

**Deliverables:**
1. Google Vision API client
2. TEXT_DETECTION integration
3. OBJECT_LOCALIZATION integration
4. Raw Vision response parsing

**Vision API Setup:**
```python
from google.cloud import vision

def analyze_image(image_bytes: bytes) -> dict:
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=image_bytes)

    # Request both features
    features = [
        vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
        vision.Feature(type_=vision.Feature.Type.OBJECT_LOCALIZATION),
    ]

    response = client.annotate_image({
        'image': image,
        'features': features
    })

    return {
        'text_annotations': response.text_annotations,
        'objects': response.localized_object_annotations
    }
```

### iOS (Days 4-8)

**Deliverables:**
1. `RatingBadge` component with confidence-based opacity
2. `OverlayContainerView` positioning badges on image
3. Top-3 emphasis logic (glow, larger size)
4. `StaticTestView` for development testing
5. Collision avoidance in OverlayMath

**RatingBadge Specs:**
- Base size: 44x24pt
- Top-3 size: 52x28pt
- Background: #000000 @ 70%
- Text: White, SF Pro Rounded Bold
- Drop shadow: 2pt blur

**Confidence-Based Opacity:**
| Confidence | Opacity | Tap Enabled |
|------------|---------|-------------|
| ≥ 0.85 | 1.0 | Yes |
| 0.65–0.85 | 0.75 | Yes |
| 0.45–0.65 | 0.5 | No |
| < 0.45 | Hidden | No |

### Gate 2 Criteria

**Backend:**
- [ ] Vision API authenticates successfully
- [ ] TEXT_DETECTION returns OCR for test images
- [ ] OBJECT_LOCALIZATION detects bottles
- [ ] Bounding boxes are normalized (0-1)
- [ ] API latency <2 seconds per request

**iOS:**
- [ ] Rating badges render at correct positions
- [ ] Opacity matches confidence thresholds
- [ ] Top-3 badges have glow/larger size
- [ ] Badges readable at arm's length
- [ ] Collision avoidance prevents overlap

---

## Phase 3: OCR Pipeline + Interaction Layer

### Backend (Days 8-12)

**Deliverables:**
1. OCR text grouping algorithm (text → bottle assignment)
2. Text normalization (remove years, sizes, marketing)
3. Mock ratings database (100+ wines)
4. Fuzzy matching for wine lookup
5. Full pipeline integration

**OCR Grouping Algorithm:**
```python
def group_text_to_bottles(ocr_results, bottle_bboxes):
    """Assign OCR text fragments to nearest bottle."""
    grouped = {bottle.id: [] for bottle in bottle_bboxes}

    for text_block in ocr_results:
        text_center = get_centroid(text_block.bounding_poly)
        nearest_bottle = find_nearest_bottle(text_center, bottle_bboxes)
        if nearest_bottle and distance < PROXIMITY_THRESHOLD:
            grouped[nearest_bottle.id].append(text_block.text)

    return grouped
```

**Normalization Rules:**
- Remove years: `\b(19|20)\d{2}\b`
- Remove sizes: `\b\d+\s*(ml|ML|L)\b`
- Remove prices: `\$\d+\.?\d*`
- Strip marketing words: "reserve", "special edition", etc.

**Ratings Database Schema:**
```json
{
  "wines": [{
    "canonical_name": "Chateau Margaux",
    "aliases": ["Ch Margaux"],
    "rating": 4.8,
    "source": "vivino"
  }]
}
```

### iOS (Days 8-11)

**Deliverables:**
1. `WineDetailSheet` component
2. Tap gesture on badges (confidence ≥0.65 only)
3. Confidence labels ("Widely rated" / "Limited data")
4. Swipe-to-dismiss sheet

**Detail Sheet Content:**
- Wine name (headline)
- Star rating (large, 1-5 scale)
- Confidence label
- Minimal height (~200pt)

### Gate 3 Criteria

**Backend:**
- [ ] Text correctly assigned to bottles (manual verification)
- [ ] Years/sizes removed from normalized names
- [ ] Fuzzy matching finds wines with typos
- [ ] Unknown wines go to fallback_list
- [ ] End-to-end response <3 seconds

**iOS:**
- [ ] Tap high-confidence badge → sheet opens
- [ ] Tap low-confidence badge → nothing happens
- [ ] "Widely rated" shown for confidence ≥0.85
- [ ] "Limited data" shown for 0.65-0.85
- [ ] Swipe down dismisses sheet

---

## Phase 4: Full Integration + Camera

### Backend (Days 12-14)

**Deliverables:**
1. Deploy to Google Cloud Run (staging)
2. Environment configuration (staging URL)
3. Health check endpoint
4. Error response handling

**Cloud Run Deployment:**
```bash
gcloud run deploy wine-scanner-staging \
  --source backend/ \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 1
```

### iOS (Days 12-15)

**Deliverables:**
1. Camera permission setup (Info.plist)
2. `CameraView` using UIImagePickerController
3. Real `ScanAPIClient` with async/await
4. Environment switching (local/staging)
5. Loading state during processing
6. Error handling with retry

**Info.plist:**
```xml
<key>NSCameraUsageDescription</key>
<string>Wine Shelf Scanner needs camera access to photograph wine shelves and show you ratings.</string>
```

**App Flow States:**
```swift
enum ScanState {
    case idle           // Show camera button
    case capturing      // Camera view
    case processing     // Loading overlay
    case results        // Overlays on photo
    case error          // Error with retry
}
```

### Integration Testing

**E2E Test Checklist:**
- [ ] iOS connects to staging backend
- [ ] Photo uploads successfully
- [ ] Response parses correctly
- [ ] Overlays render on correct bottles
- [ ] Detail sheet works
- [ ] End-to-end <4 seconds

### Gate 4 Criteria

**Backend:**
- [ ] Staging URL accessible: `https://wine-scanner-staging-xxx.run.app`
- [ ] `/scan` endpoint works from external network
- [ ] Health check returns 200

**iOS:**
- [ ] Camera permission prompt appears
- [ ] Photo captured and uploaded
- [ ] Loading state displays during processing
- [ ] Results render after API response
- [ ] Error state shows retry option
- [ ] Works with `--use-mocks` flag

---

## Phase 5: Polish + TestFlight

### iOS (Days 15-18)

**Deliverables:**
1. Toast for partial detection
2. Fallback list view
3. App icon and launch screen
4. Performance optimization
5. Crash reporting (Firebase Crashlytics)

**Failure Handling:**

| Scenario | UI Response |
|----------|-------------|
| Partial detection | Toast: "Some bottles couldn't be recognized" + show detected |
| No bottles detected | Auto-switch to fallback list |
| Network error | Error screen with retry button |
| Timeout | Error screen with retry button |

**TestFlight Metadata:**
- App name: "Wine Shelf Scanner"
- Description: "Point at a wine shelf, get instant ratings."
- Test notes: What to test, known issues

### Beta Testing Plan

**Internal (Week 1):**
- Team members only
- Focus: crashes, obvious bugs
- Target: 5-10 testers

**External (Weeks 2-3):**
- Recruit 20-50 wine buyers
- Test varied scenarios
- Collect feedback on accuracy

### Gate 5 Criteria

- [ ] Partial detection shows toast
- [ ] Full failure shows fallback list
- [ ] No dead-end states
- [ ] End-to-end <4 seconds
- [ ] Crash rate <1%
- [ ] TestFlight build uploaded
- [ ] Beta review approved
- [ ] 10+ external testers recruited

---

## Phase 6: App Store Submission

### App Store Metadata

**Required:**
- App name (30 chars max)
- Subtitle: "Instant Ratings on Any Shelf"
- Category: Food & Drink
- Privacy policy URL
- Screenshots (6.7", 6.5", 5.5")

**Screenshots Needed:**
1. Camera view with "Scan" button
2. Results with overlays on bottles
3. Detail sheet with wine info
4. Before/after comparison

### Privacy Compliance

- Camera usage: explained, not stored
- Photos: processed on server, then deleted
- No user accounts
- No tracking

### Gate 6 Criteria

- [ ] All metadata complete
- [ ] Screenshots uploaded
- [ ] Privacy policy published
- [ ] Build uploaded and processed
- [ ] Submitted for review
- [ ] **APPROVED**

---

## Critical Files Reference

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Technical spec, API contract |
| `PRD.md` | Product requirements |
| `TODO.md` | Implementation checklist |
| `PLAN.md` | This development plan |
| `ios/OverlayMath.swift` | Overlay placement logic |
| `backend/main.py` | FastAPI entry point |
| `backend/app/services/vision.py` | Vision API client |
| `backend/app/data/ratings.json` | Wine ratings database |

---

## Commands Reference

**Backend:**
```bash
# Local development
cd Backend && uvicorn main:app --reload

# Run tests
cd Backend && pytest tests/ -v

# Deploy to Cloud Run
gcloud run deploy wine-scanner-staging --source backend/
```

**iOS:**
```bash
# Open in Xcode
open ios/WineShelfScanner.xcodeproj

# Build for testing
xcodebuild -scheme WineShelfScanner -destination 'platform=iOS Simulator,name=iPhone 15'

# Run with mocks
# Add --use-mocks to scheme arguments
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Vision API accuracy | Fallback list for undetected bottles |
| Slow API response | Loading state + 10s timeout |
| App Store rejection | Pre-submission checklist, privacy compliance |
| Cold start latency | Min 1 instance on Cloud Run |
| Beta tester recruitment | Use TestFlight communities, wine forums |

---

## Resolved Prerequisites

| Item | Status | Notes |
|------|--------|-------|
| Apple Developer Account | Deferred | User has account on personal machine, will verify at Phase 5 |
| Google Cloud Account | Ready | Existing account with billing |
| Test Images | Stock images | Source from Unsplash/Pexels (wine shelf photos) |
| OCR Normalization | Both approaches | Heuristics first, LLM interface ready for cheap options |

---

## LLM Options for OCR Normalization (Cost Comparison)

| Model | Cost per 1K tokens | Notes |
|-------|-------------------|-------|
| **Gemini 1.5 Flash** | Free tier (15 RPM) | Best for starting - free! |
| **Claude 3 Haiku** | $0.25 input / $1.25 output | Very cheap, high quality |
| **GPT-4o Mini** | $0.15 input / $0.60 output | Budget OpenAI option |
| **Ollama (local)** | Free | Requires local setup, not for production |

**Recommendation:** Start with heuristics, add Gemini Flash (free tier) as first LLM option.

---

## Test Image Sources

Stock image sites with wine shelf photos:
- Unsplash: "wine shelf", "liquor store wine"
- Pexels: "wine bottles shelf"
- Getty Images (watermarked for dev only)

Collect 15-20 varied test images during Phase 0.
