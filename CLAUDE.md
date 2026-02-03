# Wine Shelf Scanner

## Goal
Photo-based wine shelf scanner. Take photo → see ratings overlaid on bottles → choose confidently in <10 seconds.

## Non-Goals (Strict)
- Live AR scanning (post-MVP consideration only)
- Accounts/auth
- Social features
- Price comparison
- Recommendations/recommendation engine
- Purchase links
- Real-time web scraping

If it doesn't help the user choose a bottle faster, leave it out.

---

## Project Status

See `ROADMAP.md` for current project status and next steps.

---

## Directory Structure
```
wine-shelf-scanner/
├── backend/
│   ├── app/
│   │   ├── config.py         # Centralized configuration
│   │   ├── models/           # Pydantic response models
│   │   ├── routes/           # FastAPI endpoints
│   │   ├── services/         # Vision API, OCR, wine matching, LLM
│   │   ├── mocks/            # Mock fixtures for testing
│   │   ├── ingestion/        # Data pipeline (adapters, normalizers)
│   │   └── data/
│   │       └── wines.db      # SQLite database (191K wines)
│   ├── scripts/              # CLI tools (ingest, benchmark, capture)
│   └── tests/
│       ├── e2e/              # Playwright browser tests
│       ├── accuracy/         # Recognition accuracy tests
│       └── fixtures/         # Captured Vision API responses
├── ios/                      # SwiftUI iOS app
├── expo/                     # React Native app (Expo SDK)
├── nextjs/                   # Next.js web app (Vercel deployment)
├── raw-data/                 # Wine data sources (Kaggle, Vivino)
├── test-images/              # Test assets for Vision API
├── ROADMAP.md                # Project status (single source of truth)
├── PRD.md                    # Product requirements (canonical)
├── README.md                 # Quick start guide
└── CLAUDE.md                 # This file
```

## Frontend Development Strategy

**Current:** iOS, Expo, and Next.js are developed in parallel. Neither is the source of truth.

**Frontends:**
- **iOS** — Native SwiftUI app
- **Expo** — React Native for iOS/Android
- **Next.js** — Web app deployed to Vercel

All frontends implement the same API contract and UX rules, but maintain separate codebases. The Next.js web app shares lib utilities (types, theme, overlay-math) ported from Expo.

---

## API Contract (DO NOT CHANGE)

```json
{
  "image_id": "string",
  "results": [
    {
      "wine_name": "string",
      "rating": 4.6,
      "confidence": 0.92,
      "bbox": {
        "x": 0.25,
        "y": 0.40,
        "width": 0.10,
        "height": 0.30
      }
    }
  ],
  "fallback_list": [
    {
      "wine_name": "string",
      "rating": 4.3
    }
  ]
}
```

- Bounding boxes are normalized (0–1)
- UI relies on this contract — do not add/remove fields

---

## Overlay Placement Math

All math must be centralized in `OverlayMath.swift` (no magic numbers in views).

### Anchor Point
```
anchor_x = bbox.x + bbox.width / 2
anchor_y = bbox.y + bbox.height * 0.25
```

### SwiftUI Mapping
```swift
screen_x = anchor_x * geo.width
screen_y = anchor_y * geo.height
```

### Occlusion Rule
If `bbox.height < 0.15` → treat as partial bottle, anchor at top-most visible region.

### Collision Avoidance
If overlay overlaps label text:
- Shift upward by 5–10% of bbox height
- Clamp to image bounds

---

## Confidence-Based UX Rules

| Confidence | Opacity | Tap Enabled | Notes |
|------------|---------|-------------|-------|
| ≥ 0.85     | 1.0     | Yes         | Full emphasis |
| 0.65–0.85  | 0.75    | Yes         | Normal |
| 0.45–0.65  | 0.5     | No          | De-emphasized |
| < 0.45     | Hidden  | No          | Fallback list only |

Low-confidence overlays:
- Never get top-3 emphasis
- Never open detail sheet

---

## Top-3 Emphasis Logic

1. Sort visible bottles by rating
2. Top 3 get:
   - Slight glow or thicker stroke
   - Slightly larger rating badge
3. Do NOT hide lower-rated bottles

---

## Detail Sheet (On Tap)

Tap rating badge → modal sheet.

**Content (max):**
- Wine name (headline)
- Star rating (large)
- Confidence label:
  - "Widely rated" (high confidence ≥0.85)
  - "Limited data" (medium confidence 0.65–0.85)
- Optional 1–2 sentence summary (future)

**Rules:**
- No scrolling if possible
- Swipe down to dismiss
- Must feel fast and lightweight

---

## Failure Handling

### Partial Detection
- Show overlays that passed confidence threshold
- Toast: "Some bottles couldn't be recognized"

### Full Failure
- Auto-switch to fallback list view
- Sort by rating descending
- Never show a dead end

---

## Backend Pipeline

### Tiered Recognition Pipeline

1. Receive image at `/scan`
2. Google Vision API:
   - `TEXT_DETECTION` (OCR)
   - `OBJECT_LOCALIZATION` (bottles)
3. Group OCR text by spatial proximity (15% threshold)
4. Normalize text:
   - Remove years (19xx, 20xx)
   - Remove sizes (750ml, 1L)
   - Remove prices and marketing text
5. **Tiered Recognition:**
   - **Step 1:** Enhanced fuzzy match (rapidfuzz + phonetic)
   - **Step 2:** If confidence < 0.7 → LLM normalization (Claude Haiku or Gemini)
   - **Step 3:** Re-match LLM-normalized result against database
6. Filter by confidence:
   - ≥ 0.45 → main results array
   - < 0.45 → fallback list only
7. Return response using schema above

### Key Implementation Details

- LLM normalizer is protocol-based (`NormalizerProtocol`) — swappable between Claude and Gemini
- Fuzzy matching uses multi-algorithm scoring: ratio (45%), partial_ratio (30%), token_sort (25%)
- Phonetic matching via jellyfish metaphone for pronunciation-based matches
- N-gram indexing for performance optimization

### Debug Endpoint

`GET /scan/debug` — Returns raw OCR text, extracted wine names, and bottle count for troubleshooting.

### Query Parameters

- `use_vision_api` — Toggle real vs mock Vision API
- `use_llm` — Toggle LLM fallback (default: true)
- `mock_scenario` — Select fixture (full_shelf, partial_detection, etc.)

---

## Paywall Rules

> **Status:** Designed but not yet implemented (Phase 5 work).

- Never block first successful scan
- Allow 3–5 free scans
- Show paywall AFTER results render (never before value)
- Copy: "Want unlimited instant ratings? Unlock scans."
- No hard interrupt. No modal before value.

---

## Tech Stack

### iOS
- SwiftUI
- iOS 16+
- Native camera (photo capture only, no live video)
- Declarative overlay rendering

### Expo
- React Native (Expo SDK)
- TypeScript
- expo-image-picker for camera/library
- Same API contract as iOS
- Centralized theming in `expo/lib/theme.ts`

### Next.js (Web)
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Deployed to Vercel
- File upload + camera capture (mobile browsers)
- Shared lib utilities ported from Expo

### Backend
- FastAPI (Python 3.9+)
- Google Cloud Vision API
- LLM Normalizer (dual-provider, behind protocol interface):
  - Claude Haiku (default, via `ANTHROPIC_API_KEY`)
  - Google Gemini 2.0 Flash (via `GOOGLE_API_KEY` + `LLM_PROVIDER=gemini`)
- rapidfuzz (multi-algorithm fuzzy matching)
- jellyfish (phonetic matching)
- SQLite with FTS5 (191K wine database)

---

## Commands

### Backend
```bash
# Start dev server
cd backend && source venv/bin/activate && uvicorn main:app --reload

# Run tests (152 tests)
cd backend && pytest tests/ -v

# Data ingestion (refresh wine database)
cd backend && python -m app.ingestion.ingest

# Accuracy benchmarking
cd backend && python scripts/accuracy_report.py

# Capture Vision API response (for test fixtures)
cd backend && python scripts/capture_vision_response.py <image_path>
```

### iOS
```bash
# Open project
open ios/WineShelfScanner.xcodeproj

# Run tests
xcodebuild test -scheme WineShelfScanner -destination 'platform=iOS Simulator,name=iPhone 15'
```

### Expo
```bash
# Install dependencies
cd expo && npm install

# Start dev server
npm start

# Run on iOS simulator
npm run ios

# Run on Android emulator
npm run android

# Run tests
npm test
```

### Next.js (Web)
```bash
# Install dependencies
cd nextjs && npm install

# Start dev server
npm run dev

# Build for production
npm run build

# Run tests
npm test

# Type check
npm run type-check
```

### Deployment
```bash
# Deploy backend to Cloud Run
./deploy.sh PROJECT_ID

# Deploy web to Vercel (auto-deploys on push, or manual)
cd nextjs && vercel
```

### Vercel Environment Variables
Set these in the Vercel dashboard for production:
- `NEXT_PUBLIC_API_BASE_URL` — Backend API URL (e.g., https://wine-scanner-api-xxx.run.app)
- `NEXT_PUBLIC_DEBUG_MODE` — Set to "false" for production

### Backend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MOCKS` | `false` | Use mock data instead of Vision API |
| `USE_SQLITE` | `true` | Use SQLite database (wines.db) instead of JSON |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | Path to GCP service account JSON |
| `LLM_PROVIDER` | `claude` | LLM for OCR normalization (`claude` or `gemini`) |
| `ANTHROPIC_API_KEY` | - | API key for Claude Haiku |
| `GOOGLE_API_KEY` | - | API key for Gemini |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DEV_MODE` | `false` | Enable verbose logging |

---

## Performance Targets

- End-to-end scan: ≤ 4 seconds
- Battery friendly (single image processing)

---

## Success Criterion

A casual user can:
1. Take one photo
2. Instantly see which bottles are best
3. Choose confidently in under 10 seconds

If something doesn't serve this, cut it.
