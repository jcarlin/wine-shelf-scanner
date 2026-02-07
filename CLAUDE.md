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
├── nextjs/                   # Next.js web app (Vercel deployment)
├── raw-data/                 # Wine data sources (Kaggle, Vivino)
├── test-images/              # Test assets for Vision API
├── ROADMAP.md                # Project status (single source of truth)
├── PRD.md                    # Product requirements (canonical)
├── README.md                 # Quick start guide
└── CLAUDE.md                 # This file
```

## Frontend Development Strategy

**Current:** iOS and Next.js are developed in parallel. Neither is the source of truth.

**Frontends:**
- **iOS** — Native SwiftUI app
- **Next.js** — Web app deployed to Vercel

All frontends implement the same API contract and UX rules, but maintain separate codebases.

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
- Confidence label: "Widely rated" (shown only for high confidence ≥0.85)
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
- Optional "Report" link on toast (feature-flagged: `bugReport`)

### Full Failure
- Auto-switch to fallback list view
- Sort by rating descending
- Never show a dead end
- "Not what you expected? Report an issue" link at bottom of fallback list

### Bug Report (Feature-Flagged)
- "Report an Issue" button appears on error screen, partial detection toast, and fallback list
- Opens a lightweight report sheet/modal
- Auto-captures: error type, error message, image ID, device ID, platform, app version, timestamp
- Optional free-text field (max 500 chars)
- Fire-and-forget submission — always shows success, never blocks the user
- Backend: `POST /report` → stores in `bug_reports` SQLite table
- Feature flag: `feature_bug_report` (iOS) / `NEXT_PUBLIC_FEATURE_BUG_REPORT` (Next.js)

---

## Backend Pipeline — Detailed Scan Flow

### Entry Point: `POST /scan` → `routes/scan.py:scan_shelf()`

The scan endpoint receives an image and runs it through a multi-stage pipeline. Each stage has fallbacks for unmatched bottles, making the pipeline progressively more expensive but more thorough.

### Stage 1: Image Upload & Validation (~50ms)
**File:** `routes/scan.py:326-376`
- Validate content type (JPEG, PNG, HEIC/HEIF)
- Generate UUID `image_id`
- Read image bytes, convert HEIC→JPEG if needed (`convert_heic_to_jpeg()`)
- Validate file size (≤10MB)

### Stage 2: Google Vision API (~2-3s) — BIGGEST SINGLE COST
**Files:** `services/vision.py:91-120`, `services/vision_cache.py`
- **Cache check first:** SHA256 hash of image bytes → lookup in `vision_cache` table
  - Cache key: `image_hash` (SHA256 of raw bytes)
  - Stores gzip-compressed JSON of `VisionResult`
  - TTL: 7 days, max 500MB, LRU eviction
  - **PRODUCTION: VISION_CACHE_ENABLED=false** (cache is disabled!)
- **API call:** Single `annotate_image()` with two features:
  - `OBJECT_LOCALIZATION` → detect bottles (filter for "bottle"/"wine"/"drink")
  - `TEXT_DETECTION` → OCR all text on shelf
- **Deduplication:** IoU-based overlap removal for duplicate bottle detections
- **Output:** `VisionResult` with `objects[]`, `text_blocks[]`, `raw_text`

### Stage 3: OCR Text Grouping (~10ms)
**File:** `services/ocr_processor.py`
- `OCRProcessor.process_with_orphans()` assigns text blocks to bottles by spatial proximity
- Proximity threshold: 25% of image dimensions (`Config.PROXIMITY_THRESHOLD`)
- Each `BottleText` gets: raw `combined_text` + `normalized_name` (years/sizes/noise removed)
- **Orphaned texts:** Text blocks not near any bottle → saved for later fallback matching
- Output: `bottle_texts[]` (one per bottle) + `orphaned_texts[]`

### Stage 4: Tiered DB Matching (~100-500ms)
**File:** `services/recognition_pipeline.py:303-391`

**Phase 4a: Parallel Fuzzy Match** (ThreadPoolExecutor, 4 workers)
For each bottle's `normalized_name`, runs `WineMatcher.match()`:
1. **Exact match** → `find_by_name()` on `wines` + `wine_aliases` tables (confidence=1.0)
2. **FTS5 prefix** → `search_fts()` on `wine_fts` table, limit=5 candidates (confidence≤0.95)
3. **Fuzzy match** → `search_fts_or()` limit=50 candidates, scored with:
   - `fuzz.ratio` (45%) + `fuzz.partial_ratio` (30%) + `fuzz.token_sort_ratio` (25%)
   - +0.05 phonetic bonus via `jellyfish.metaphone`
   - Threshold: 0.72 (`FUZZY_CONFIDENCE_THRESHOLD`)
- **Module-level cache:** `_match_cache` dict (max 500 entries, LRU eviction)

**Phase 4b: Confidence Partition**
- ≥0.85 confidence → **high-confidence**, skip LLM entirely
- <0.85 confidence → **needs LLM validation**

### Stage 5: LLM Batch Validation (~1-3s per batch) — SECOND BIGGEST COST
**Files:** `services/recognition_pipeline.py:451-547`, `services/llm_normalizer.py`

**Cache check first:** For each item needing LLM, check `llm_ratings_cache` table:
- Keys checked: `combined_text` (raw OCR) AND `normalized_name`
- Lookup: `WHERE LOWER(wine_name) = ?` (case-insensitive)
- **Cache hit:** Return cached wine name, rating, metadata → skip LLM call
- **Cache miss:** Add to batch for LLM

**LLM call:** Single batched call via LiteLLM (`validate_batch()`)
- Provider: Gemini 2.0 Flash (production default, `LLM_PROVIDER=gemini`)
- Sends all unmatched OCR texts + optional DB candidates in one prompt
- Returns: wine name, confidence, estimated rating, metadata per item
- **Cache write:** On success, caches under canonical name + raw OCR text + normalized name

**Post-LLM processing:**
- If LLM confirms DB match → use DB wine + rating
- If LLM rejects → try re-matching LLM name against DB (≥0.95 threshold)
- If not in DB → use LLM name + LLM-estimated rating (confidence capped at 0.75)

### Stage 6: Claude Vision Fallback (~3-6s) — THIRD BIGGEST COST
**File:** `services/claude_vision.py`, triggered from `routes/scan.py:487-606`

Bottles sent to Vision if:
- Unmatched by pipeline, OR
- Matched but confidence < 0.65 (non-tappable), OR
- Matched but rating is None

**Process:**
- Compress image to ≤5MB JPEG
- Build prompt with bottle locations (bbox %) and OCR hints
- Call Claude Haiku (`claude-3-haiku-20240307`) with base64 image
- Sync call wrapped in `asyncio.run_in_executor`
- Parse JSON response → `VisionIdentifiedWine` list
- Confidence: floored at 0.65, capped at 0.70 (ensures tappable, never top-3)
- **Cache write:** Results cached in `llm_ratings_cache` under wine name + OCR text

### Stage 7: LLM Batch Rescue (~1-3s)
**File:** `routes/scan.py:608-738`

Final catch-all for remaining unmatched bottles AND orphaned texts:
- Sends ALL remaining raw OCR text to LLM in single batch call
- Cross-references fragments across the whole shelf
- Results: bottles → added to `recognized[]`, orphans → added to `fallback[]`
- DB re-match attempted for each LLM result

### Stage 8: Post-Processing (~50-100ms)
**File:** `routes/scan.py:740-850`
- `_enrich_with_reviews()` → fetch review stats + snippets from `wine_reviews` table
- Deduplicate by wine name (keep highest confidence)
- Partition: ≥0.45 confidence → `results[]`, <0.45 → `fallback[]`
- Process orphaned texts through `WineMatcher.match()` → add to fallback
- Sort results by rating descending
- Apply feature flags (pairings, safe pick, trust signals)
- `sync_discovered_wines()` → write LLM/Vision results back to DB
- Build `PipelineStats` and `DebugData`

### Estimated Timing Breakdown (14s total on production)

| Stage | Time | Notes |
|-------|------|-------|
| Upload + validation | ~50ms | Negligible |
| Google Vision API | ~2-3s | No cache on production |
| OCR grouping | ~10ms | CPU-only, fast |
| DB matching (parallel) | ~100-500ms | FTS5 + fuzzy, 4 threads |
| LLM batch validation | ~1-3s | Gemini Flash, depends on batch size |
| Claude Vision fallback | ~3-6s | Only for unmatched bottles |
| LLM batch rescue | ~1-3s | Only if bottles still unmatched |
| Post-processing | ~50-100ms | DB queries for reviews |
| **Cold start overhead** | **+2-5s** | **Cloud Run scale-from-zero** |

### Caching Architecture

| Cache | Storage | Key | Status on Prod | Impact |
|-------|---------|-----|----------------|--------|
| Vision API cache | `vision_cache` table | SHA256(image_bytes) | **DISABLED** | ~2-3s savings |
| LLM rating cache | `llm_ratings_cache` table | `LOWER(wine_name)` | Enabled | ~1-3s savings per cache hit |
| Wine matcher cache | In-memory dict | `query.lower()` | Enabled (per-instance) | ~ms savings, repeated names |
| WineMatcher singleton | `@lru_cache(1)` | N/A | Enabled | Avoids re-creating matcher |

### Known Caching Issues

1. **Vision cache disabled on production** (`VISION_CACHE_ENABLED=false` in service.yaml). This means every scan pays the full 2-3s Vision API cost even for the same image.
2. **LLM cache key mismatch risk:** Cache writes use `wine_name.strip()` (original case) but lookups use `LOWER(wine_name)`. The `ON CONFLICT(wine_name)` uses exact case. If the same wine is cached as "Caymus" and looked up as "caymus cabernet sauvignon NAPA VALLEY 2021" (the raw OCR text), it won't match. The cache also stores under raw OCR text, but OCR text varies by image angle/quality, so cache hits are uncommon for new images.
3. **No index on `LOWER(wine_name)`** in `llm_ratings_cache` — lookups do a full table scan with `WHERE LOWER(wine_name) = ?`.
4. **Per-instance in-memory cache:** The `_match_cache` dict in `wine_matcher.py` is not shared across Cloud Run instances. Each new instance starts cold.

### Debug Endpoint

`POST /scan/debug` — Returns raw OCR text, extracted wine names, and bottle count for troubleshooting.

### Query Parameters

- `use_vision_api` — Toggle real vs mock Vision API
- `use_llm` — Toggle LLM fallback (default: true)
- `use_vision_fallback` — Toggle Claude Vision fallback (default: true)
- `debug` — Include pipeline debug info in response
- `mock_scenario` — Select fixture (full_shelf, partial_detection, etc.)
- `use_vision_fixture` — Path to captured Vision API fixture for replay

### Bug Report Endpoint

`POST /report` — Receives bug reports from clients.

```json
{
  "report_type": "error | partial_detection | full_failure | wrong_wine",
  "error_type": "NETWORK_ERROR | SERVER_ERROR | TIMEOUT | PARSE_ERROR",
  "error_message": "string",
  "user_description": "string (optional, max 500)",
  "image_id": "string (optional)",
  "device_id": "string",
  "platform": "ios | web | expo",
  "app_version": "string",
  "timestamp": "ISO 8601",
  "metadata": {
    "wines_detected": 0,
    "wines_in_fallback": 5,
    "confidence_scores": [0.42, 0.38]
  }
}
```

`GET /report/stats` — Returns aggregated bug report statistics.

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

### Next.js (Web)
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Deployed to Vercel
- File upload + camera capture (mobile browsers)
- Centralized lib utilities (types, theme, overlay-math)

### Backend
- FastAPI (Python 3.9+)
- Google Cloud Vision API
- LLM Normalizer (dual-provider, behind protocol interface):
  - Claude Haiku (default, via `ANTHROPIC_API_KEY`)
  - Google Gemini 2.0 Flash (via `GOOGLE_API_KEY` + `LLM_PROVIDER=gemini`)
- rapidfuzz (multi-algorithm fuzzy matching)
- jellyfish (phonetic matching)
- SQLite with FTS5 (191K wine database)
- Alembic for database migrations (single source of truth for schema)

### Database Schema

**All schema changes must go through Alembic migrations.**

Tables are created by migrations in `backend/alembic/versions/`:
- Migration 001: Core tables (wines, wine_aliases, wine_sources, wine_fts, llm_ratings_cache, corrections, wine_reviews)
- Migration 002: bug_reports
- Migration 003: vision_cache

To add a new table or modify schema:
1. Create a new migration: `cd backend && alembic revision -m "description"`
2. Edit the generated file in `alembic/versions/`
3. Test locally: `alembic upgrade head`
4. Migrations run automatically on Cloud Run deploy via `startup.py`

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

# Wine promotion (review/promote LLM-discovered wines to DB)
cd backend && python -m scripts.promote_wines --preview
cd backend && python -m scripts.promote_wines --promote "Wine Name"
```

### iOS
```bash
# Open project
open ios/WineShelfScanner.xcodeproj

# Run tests
xcodebuild test -scheme WineShelfScanner -destination 'platform=iOS Simulator,name=iPhone 15'
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
# Deploy backend to Cloud Run (manual)
cd backend/deploy && ./deploy.sh [project-id]

# Deploy backend via GitHub Actions (automatic)
# Push to main branch triggers deploy (see .github/workflows/deploy.yml)

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
| `DEBUG_MODE` | `false` | Include debug info in scan responses and enable verbose logging |
| `USE_LLM_CACHE` | `true` | Cache LLM/Vision-discovered wines for promotion to DB |
| `USE_FAST_PIPELINE` | `false` | Enable single-pass multimodal LLM pipeline (replaces legacy 5-stage) |
| `FAST_PIPELINE_MODEL` | `gemini-2.0-flash` | Multimodal model for fast pipeline |
| `FAST_PIPELINE_TIMEOUT` | `15.0` | Timeout in seconds for fast pipeline LLM call |
| `FAST_PIPELINE_FALLBACK` | `true` | Fall back to legacy pipeline if fast pipeline fails |

---

## Performance Targets

- End-to-end scan: ≤ 4 seconds (current: ~14s on production)
- Battery friendly (single image processing)

---

## Performance Investigation (2026-02-06)

### Current State: ~14s for test-images/wine1.jpg on production

### Where Time Is Spent (worst case, all stages triggered)

The pipeline is **sequential and additive** — every unmatched bottle adds more stages:
1. Google Vision API: **2-3s** (no cache on prod)
2. Fuzzy matching: **100-500ms** (fast, parallelized)
3. LLM batch validation: **1-3s** (Gemini Flash)
4. Claude Vision fallback: **3-6s** (Haiku with image)
5. LLM batch rescue: **1-3s** (Gemini Flash, another call)
6. Cold start: **+2-5s** (Cloud Run scale-from-zero)

**Key insight:** The 14s is NOT a single slow step — it's the cascade of 3-4 external API calls that each take 1-6s.

### Optimization Opportunities (Ranked by Impact)

#### 1. Enable Vision Cache on Production (saves 2-3s on repeat scans)
`VISION_CACHE_ENABLED=false` in service.yaml. Setting to `true` would eliminate the Vision API call for previously-scanned images. The cache table and logic already exist.
- **Risk:** Cache grows with each unique image. But eviction logic (LRU, 500MB max) is already implemented.
- **Caveat:** Only helps repeat scans of same image bytes. Different photo = different hash = cache miss.

#### 2. Parallelize LLM Calls (saves 3-6s)
Currently Vision API → matching → LLM validation → Claude Vision → LLM rescue run **strictly sequentially**. The Claude Vision call and LLM batch validation could potentially run in parallel since they operate on different bottle subsets.

#### 3. Eliminate Claude Vision Stage for "Good Enough" Results
The Vision fallback fires for ANY unmatched or low-confidence bottle. Consider:
- Skip Vision fallback if ≥80% of bottles already matched with confidence ≥0.65
- Only call Vision for bottles with zero match (not just low-confidence)
- This would remove the entire 3-6s stage for most real-world shelves

#### 4. Add Server-Side Timing Instrumentation
There is NO timing instrumentation in the pipeline. Add `time.perf_counter()` measurements to each stage so we can measure actual production timing breakdown per stage.

#### 5. Improve LLM Cache Hit Rate
- Add index: `CREATE INDEX idx_llm_cache_lower_name ON llm_ratings_cache(wine_name COLLATE NOCASE)`
- Cache under more normalized keys (strip common OCR noise before lookup)
- The cache currently stores under 3 keys per wine (canonical, OCR, normalized), but lookups only check 2

#### 6. Pre-warm Cloud Run (saves 2-5s cold start)
`autoscaling.knative.dev/minScale: "0"` means instances scale to zero. Setting to `"1"` keeps one warm instance alive. Costs ~$10-20/month but eliminates cold start.

#### 7. Reduce Unnecessary LLM Calls
- `HIGH_CONFIDENCE_THRESHOLD=0.85` means wines with 0.72-0.84 confidence go to LLM even though they're already above `FUZZY_CONFIDENCE_THRESHOLD=0.72`. Consider raising the skip-LLM threshold or accepting more fuzzy matches without validation.

#### 8. Will Having More DB Entries Help?
**Partially yes.** More wines in the DB means more bottles get matched in Stage 4 (fast, ~100-500ms) instead of falling through to Stage 5-7 (slow, ~2-12s of LLM/Vision calls). The LLM stages exist specifically as fallback for wines NOT in the DB. However:
- The DB already has 191K wines, covering most common wines
- The `llm_ratings_cache` table acts as a growing supplementary DB
- The `wine_sync.py` module already auto-promotes LLM-discovered wines back to the DB
- **The bigger win is improving match quality** (better FTS/fuzzy scoring) so existing DB entries are found more reliably, rather than just adding more entries

#### 9. Consider Single-Pass LLM Architecture (Radical Redesign)
Instead of OCR → fuzzy match → LLM validate → Vision fallback → LLM rescue (4 serial stages), consider:
- Send the image directly to a multimodal LLM (Gemini Flash with vision) to identify ALL wines in one call
- Cross-reference LLM results against DB for ratings
- This replaces stages 2-7 with a single ~2-3s LLM call + ~100ms DB lookups
- Trade-off: Less accurate for DB-matched wines, but dramatically faster

---

## Success Criterion

A casual user can:
1. Take one photo
2. Instantly see which bottles are best
3. Choose confidently in under 10 seconds

If something doesn't serve this, cut it.
