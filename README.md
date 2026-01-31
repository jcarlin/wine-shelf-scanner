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
┌─────────────────┐     ┌─────────────────┐
│   Expo App      │     │  Ratings DB     │
│   (React Native)│     │  (SQLite)       │
└─────────────────┘     └─────────────────┘
```

### Components

| Component | Stack | Purpose |
|-----------|-------|---------|
| **iOS App** | SwiftUI, iOS 16+ | Camera capture, overlay rendering |
| **Expo App** | React Native, TypeScript | Cross-platform mobile app |
| **Backend** | FastAPI (Python 3.11+) | Image processing orchestration, wine matching |
| **Vision** | Google Cloud Vision API | OCR + bottle detection |
| **Ratings DB** | SQLite (191K wines) | Wine name → rating lookup with FTS5 search |

### Frontend Strategy

iOS is the primary frontend. Expo (React Native) is in development on the `reactive-native` branch. Both implement the same API contract and UX rules.

**Future plan:** May switch to Expo as the single source for iOS, Android, and web builds.

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

## Quick Start

### Prerequisites

- Python 3.11+
- Xcode 15+ (for iOS development)
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

### Expo Setup

```bash
cd expo

# Install dependencies
npm install

# Start development server
npm start

# Or run directly on iOS/Android
npm run ios
npm run android
```

For physical device testing, update `expo/lib/config.ts` with your Mac's IP address.

### Getting Your Mac's IP

```bash
ipconfig getifaddr en0  # WiFi
```

## Backend Pipeline

1. **Image Upload**: iOS app sends JPEG to `/scan`
2. **Vision API**:
   - `OBJECT_LOCALIZATION` → Detect bottles
   - `TEXT_DETECTION` → OCR on labels
3. **OCR Processing**: Group text fragments by proximity to bottle bounding boxes
4. **Text Normalization**: Remove years (2019, 2021), sizes (750ml), marketing text
5. **Wine Matching**: Fuzzy match normalized text against ratings database
6. **Response**: Return positioned wines and fallback list

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
│   │   ├── models/          # Pydantic response models
│   │   ├── routes/          # FastAPI endpoints
│   │   ├── services/        # Vision API, OCR, wine matching
│   │   ├── mocks/           # Mock fixtures for testing
│   │   └── data/
│   │       └── ratings.json # Wine ratings database
│   ├── tests/
│   ├── main.py              # App entry point
│   └── requirements.txt
├── ios/
│   └── WineShelfScanner/
│       ├── App/             # App entry, Config
│       ├── Models/          # ScanResponse, ScanState, ViewModel
│       ├── Views/           # UI components
│       ├── Services/        # API client, mock service
│       └── Utils/           # OverlayMath
├── expo/
│   ├── app/                 # Expo Router screens
│   ├── components/          # UI components
│   ├── hooks/               # Custom React hooks
│   └── lib/                 # API client, types, overlay math
├── PRD.md                   # Product requirements
└── CLAUDE.md                # Development context
```

## Configuration

### Backend Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MOCKS` | `true` | Use mock data instead of Vision API |
| `USE_SQLITE` | `true` | Use SQLite database (wines.db) instead of JSON |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | Path to GCP service account JSON |

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
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:WineShelfScannerUITests
```

UI tests use mock injection via launch environment variables (`USE_MOCKS`, `MOCK_SCENARIO`).

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
