# Wine Shelf Scanner

Point your phone at a wine shelf and instantly see which bottles are worth buying — with ratings overlaid directly on the bottles.

## Overview

Wine Shelf Scanner solves decision paralysis for casual wine buyers. Instead of manually searching for ratings or scanning labels one by one, take a single photo and see ratings appear directly on the bottles.

**Target**: Choose a bottle confidently in under 10 seconds.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   iOS App       │────▶│  FastAPI        │────▶│  Google Cloud    │
│   (SwiftUI)     │◀────│  Backend        │◀────│  Vision API      │
└─────────────────┘     └─────────────────┘     └──────────────────┘
        ▲                       │
        │                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   Next.js Web   │     │  Ratings DB     │     │  LLM Normalizer  │
│   (Vercel)      │     │  (SQLite 191K)  │     │  (Claude/Gemini) │
└─────────────────┘     └─────────────────┘     └──────────────────┘
```

### Components

| Component | Stack | Purpose |
|-----------|-------|---------|
| **iOS App** | SwiftUI, iOS 16+ | Camera capture, overlay rendering |
| **Next.js Web** | Next.js 14, TypeScript, Tailwind | Browser-based scanner (Vercel) |
| **Backend** | FastAPI (Python 3.9+) | Image processing orchestration, wine matching |
| **Vision** | Google Cloud Vision API | OCR + bottle detection |
| **LLM Normalizer** | Claude Haiku / Gemini 2.0 Flash | OCR text normalization fallback |
| **Ratings DB** | SQLite (191K wines) | Wine name → rating lookup with FTS5 search |

### Frontend Strategy

iOS and Next.js are developed in parallel as production-ready frontends. Both implement the same API contract and UX rules, but maintain separate codebases.

- **iOS** — Native SwiftUI app (primary)
- **Next.js** — Web app deployed to Vercel

## API Contract

```json
POST /scan
Content-Type: multipart/form-data

Response:
{
  "image_id": "uuid",
  "results": [
    {
      "wine_name": "Caymus Cabernet Sauvignon",
      "rating": 4.5,
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
      "wine_name": "Unknown Wine",
      "rating": 3.0
    }
  ]
}
```

- Bounding boxes are normalized (0–1 range)
- Ratings are on a 1–5 scale
- `fallback_list` contains wines detected but not confidently positioned

### Bug Reporting

Users can report issues from the error screen, partial detection toast, or fallback list. Reports are submitted to `POST /report` and stored in SQLite for triage.

Feature-flagged: `feature_bug_report` (iOS) / `NEXT_PUBLIC_FEATURE_BUG_REPORT` (Next.js).

## Quick Start

### Prerequisites

- Python 3.9+
- Xcode 15+ (for iOS development)
- Node.js 18+ (for Next.js)
- Google Cloud account with Vision API enabled

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# For local testing with mocks (no GCP needed):
export USE_MOCKS=true
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# For real Vision API:
export GOOGLE_APPLICATION_CREDENTIALS=./credentials.json
export USE_MOCKS=false
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### iOS Setup

1. Open `ios/WineShelfScanner.xcodeproj` in Xcode
2. Update `Config.swift` with your Mac's IP address for simulator testing:
   ```swift
   // In ios/WineShelfScanner/App/Config.swift
   return URL(string: "http://YOUR_MAC_IP:8000")!
   ```
3. Build and run on simulator or device

### Next.js Setup

```bash
cd nextjs

# Install dependencies
npm install

# Start development server
npm run dev
# Visit http://localhost:3000
```

For production, deploy to Vercel and set `NEXT_PUBLIC_API_BASE_URL` to your Cloud Run backend URL.

### Getting Your Mac's IP

```bash
ipconfig getifaddr en0  # WiFi
```

## Backend Pipeline

1. **Image Upload**: Client sends JPEG to `/scan`
2. **Vision API**:
   - `OBJECT_LOCALIZATION` → Detect bottles
   - `TEXT_DETECTION` → OCR on labels
3. **OCR Processing**: Group text fragments by proximity to bottle bounding boxes
4. **Text Normalization**: Remove years (2019, 2021), sizes (750ml), marketing text
5. **Tiered Wine Matching**:
   - **Step 1**: Enhanced fuzzy match (rapidfuzz + phonetic via jellyfish)
   - **Step 2**: If confidence < 0.7 → LLM normalization (Claude Haiku or Gemini)
   - **Step 3**: Re-match LLM-normalized result against database
6. **Filter by Confidence**:
   - ≥ 0.45 → main results array
   - < 0.45 → fallback list only
7. **Response**: Return positioned wines and fallback list

## iOS UI System

### Overlay Placement

Ratings are anchored to the upper portion of each detected bottle:

```
anchor_x = bbox.x + bbox.width / 2
anchor_y = bbox.y + bbox.height * 0.25
```

### Confidence-Based Display

| Confidence | Opacity | Tap Enabled |
|------------|---------|-------------|
| ≥ 0.85 | 1.0 | Yes |
| 0.65–0.85 | 0.75 | Yes |
| 0.45–0.65 | 0.5 | No |
| < 0.45 | Hidden | No |

### Top-3 Emphasis

The three highest-rated visible bottles get:
- Slight glow effect
- Larger rating badge

## Project Structure

```
wine-shelf-scanner/
├── backend/
│   ├── app/
│   │   ├── config.py        # Centralized configuration
│   │   ├── models/          # Pydantic response models
│   │   ├── routes/          # FastAPI endpoints
│   │   ├── services/        # Vision API, OCR, wine matching, LLM
│   │   ├── mocks/           # Mock fixtures for testing
│   │   ├── ingestion/       # Data pipeline (adapters, normalizers)
│   │   └── data/
│   │       └── wines.db     # SQLite database (191K wines)
│   ├── scripts/             # CLI tools (ingest, benchmark, capture)
│   ├── tests/
│   │   ├── e2e/             # Playwright browser tests
│   │   ├── accuracy/        # Recognition accuracy tests
│   │   └── fixtures/        # Captured Vision API responses
│   ├── main.py              # App entry point
│   └── requirements.txt
├── ios/
│   └── WineShelfScanner/
│       ├── App/             # App entry, Config
│       ├── Models/          # ScanResponse, ScanState, ViewModel
│       ├── Views/           # UI components
│       ├── Services/        # API client, mock service
│       └── Utils/           # OverlayMath
├── nextjs/
│   ├── app/                 # Next.js App Router pages
│   ├── components/          # UI components
│   └── lib/                 # Shared utilities (types, theme, overlay-math)
├── raw-data/                # Wine data sources (Kaggle, Vivino)
├── PRD.md                   # Product requirements
├── ROADMAP.md               # Project status tracking
└── CLAUDE.md                # Development context
```

## Configuration

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

The SQLite database is located at `backend/app/data/wines.db` (191K wines with FTS5 full-text search).

### iOS Build Settings

- **Debug**: Points to local backend (Mac IP)
- **Release**: Points to production Cloud Run URL

## Testing

### Backend Unit Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

### Deterministic Vision Tests

Real image tests use captured Vision API responses for determinism:

```bash
# Capture new fixtures (requires GCP credentials)
python scripts/capture_vision_response.py ../test-images/wine1.jpeg

# Run deterministic tests (no API calls)
pytest tests/test_real_images.py -v
```

Fixtures live in `tests/fixtures/vision_responses/`. Tests auto-detect and replay them.

**Test coverage:**
- `test_scan.py` / `test_scan_e2e.py` - API contract, scenarios, validation
- `test_recognition_pipeline.py` - Tiered matching, LLM fallback, confidence thresholds
- `test_llm_normalizer.py` - Normalizer protocol, mock behavior
- `test_wine_matcher.py` - Fuzzy matching, aliases
- `test_ocr_processor.py` - Text normalization
- `test_performance.py` - Response time targets (<4s)

### Backend E2E Tests (Playwright)

```bash
cd backend
pip install playwright pytest-playwright
playwright install chromium
pytest tests/e2e/ -v
```

Tests the web UI at `/app` which mirrors iOS behavior for browser-based testing.

### Mock Scenarios

The backend supports mock scenarios for testing without Vision API:

```bash
# Test specific scenario
curl -X POST "http://localhost:8000/scan?mock_scenario=full_shelf" \
  -F "image=@test.jpg"

# Scenarios: full_shelf, partial_detection, low_confidence, empty_results
```

### iOS Unit Tests

Run in Xcode: `Cmd+U`

### iOS UI Tests (XCUITest)

```bash
cd ios
xcodebuild test \
  -project WineShelfScanner.xcodeproj \
  -scheme WineShelfScanner \
  -destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
  -only-testing:WineShelfScannerUITests
```

UI tests use mock injection via launch environment variables (`USE_MOCKS`, `MOCK_SCENARIO`).

### Next.js Tests

```bash
cd nextjs
npm test           # Run unit tests
npm run type-check # TypeScript validation
```

Test coverage includes overlay placement math, mock service scenarios, API client behavior, and config validation.

## Performance Targets

- End-to-end scan: ≤ 4 seconds
- Battery friendly (single image processing, no live video)

## Non-Goals (MVP)

These are explicitly out of scope:
- Live AR scanning
- User accounts/auth
- Social features
- Price comparison
- Recommendations
- Purchase links
- Real-time web scraping

If it doesn't help choose a bottle faster, it's out.

## Deployment

### Cloud Run (Backend)

```bash
cd backend
./deploy.sh
```

See `cloudbuild.yaml` for CI/CD configuration.

### iOS

1. Update `Config.swift` production URL
2. Archive and upload to App Store Connect

## Troubleshooting

### "Mock data still showing"
- Check `USE_MOCKS` env var is `false`
- Verify `GOOGLE_APPLICATION_CREDENTIALS` is set

### "Network error" on iOS
- Verify Mac IP is correct in `Config.swift`
- Check Mac firewall allows port 8000
- Ensure `Info.plist` has `NSAllowsLocalNetworking`

### "Vision API error"
- Verify credentials path is correct
- Check Vision API is enabled in GCP Console
- Check service account has Vision AI Service Agent role

## License

Private - All rights reserved.
