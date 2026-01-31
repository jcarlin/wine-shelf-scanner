# Wine Shelf Scanner - Project Roadmap

**Last Updated:** January 31, 2026
**Single Source of Truth** for project status and next steps.

---

## Progress Overview

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| ~~0-3~~ | Foundation + OCR | ✅ Complete | All core features built |
| **4** | MVP Integration | 🔶 60% | Deploy + connect iOS |
| **5** | Code Quality & Refactor | ⏳ Not started | Before TestFlight |
| **6** | Data Ingestion | ✅ Complete | 191K wines ingested |
| **7** | TestFlight & App Store | ⏳ Not started | Ship with full database |

**Key Decision:** Data ingestion moved UP to Phase 6 (before TestFlight) because 60 wines is too limited for a useful product.

---

## Completed Phases (0-3)

### Phase 0: Prerequisites & Setup ✅
- Google Cloud Account + Vision API enabled
- Anthropic API Key (Claude Haiku integration)
- Development environment ready

### Phase 1: Foundation ✅
- FastAPI project setup with `/scan` endpoint
- iOS Xcode project with Swift models
- MockScanService + OverlayMath utility
- 4 mock fixtures (full_shelf, partial_detection, low_confidence, empty_results)

### Phase 2: Vision Integration + Static Overlays ✅
- Vision API client (TEXT_DETECTION + OBJECT_LOCALIZATION)
- RatingBadge component with confidence-based opacity
- Top-3 emphasis (glow) + collision avoidance

### Phase 3: OCR Pipeline + Interaction Layer ✅
- OCR text grouping (spatial clustering, 15% threshold)
- Enhanced fuzzy matching (rapidfuzz weighted: 30% ratio, 50% partial, 20% token_sort)
- Phonetic matching (jellyfish)
- LLM fallback (Claude Haiku for confidence < 0.7)
- WineDetailSheet with tap gestures

---

## Phase 4: MVP Integration (Current - 60%)

**Goal:** Deploy backend, connect iOS to production, verify end-to-end flow.

### Tasks

| Task | Status | Notes |
|------|--------|-------|
| Dockerfile + cloudbuild.yaml | ✅ Done | Ready to deploy |
| deploy.sh script | ✅ Done | `./deploy.sh PROJECT_ID` |
| Health check endpoint | ✅ Done | `GET /health` |
| **Deploy to Cloud Run** | ⏳ TODO | Critical path blocker |
| Camera integration | ✅ Done | UIImagePickerController |
| ScanAPIClient (async/await) | ✅ Done | Working |
| **Update production URL in Config.swift** | ⏳ TODO | Blocked on deploy |
| End-to-end test (iOS → Cloud Run) | ⏳ TODO | Blocked on deploy |
| Collect 20-30 real test images | ⏳ TODO | Medium priority |
| Verify <4 second scan time | ⏳ TODO | Performance gate |

### Gate 4 Criteria

- [ ] Backend deployed to Cloud Run (URL accessible externally)
- [ ] iOS connects to production backend successfully
- [ ] Photo upload → overlays render correctly
- [ ] End-to-end latency < 4 seconds
- [ ] Health check returns 200
- [ ] Manual test with 5+ real wine shelf photos

**Exit Condition:** iOS app works with deployed backend on real device.

---

## Phase 5: Code Quality & Refactor

**Goal:** Fix anti-patterns before TestFlight so beta testers get production-quality code.

### Critical Issues (Must Fix)

| Issue | File(s) | Fix |
|-------|---------|-----|
| **Global singleton pattern** | `backend/app/routes/scan.py` | Refactor to FastAPI `Depends()` |
| **Duplicate config** | `Config.swift` + `ScanViewModel.swift` | Single source: Config.swift |
| **Print statements** | Backend services | Replace with `logging` module |
| **Timeout mismatch** | Config.swift (15s) vs ScanService.swift (10s) | Consolidate |

### High Priority Issues

| Issue | File(s) | Fix |
|-------|---------|-----|
| Hardcoded constants scattered | `wine_matcher.py`, `ocr_processor.py` | Centralize in `backend/app/config.py` |
| Silent mock fallback | `ScanViewModel.swift` | Log when falling back to mocks |
| Magic numbers in ScanResponse | `ScanResponse.swift` | Import from OverlayMath |
| Unused legacy code | `ScanViewModel.startScan()` | Delete |

### Medium Priority

| Issue | Fix |
|-------|-----|
| No OpenAPI docs | Enable FastAPI auto-docs |
| Generic exception handling | Catch specific exceptions |
| Missing integration tests | Add e2e pipeline tests |

### Gate 5 Criteria

- [ ] No global mutable state in backend
- [ ] Single config source in iOS (Config.swift only)
- [ ] All print() replaced with logging.info/error/debug
- [ ] Timeout values match across codebase
- [ ] Constants centralized in config files
- [ ] All backend tests pass after refactor
- [ ] All iOS tests pass after refactor

**Exit Condition:** Codebase is production-quality with no known anti-patterns.

---

## Phase 6: Data Ingestion (BEFORE Launch)

**Goal:** Expand wine database from 60 wines to 150K+ wines before shipping.

**Detailed Spec:** `docs/DATA_INGESTION_PLAN.md`

### Overview

```
Current: 60 wines in ratings.json (hardcoded, JSON)
Target: 150K+ wines in SQLite + FTS5 (searchable, fast, scalable)
```

### Sub-Phases

| Sub-Phase | Name | Description | Status |
|-----------|------|-------------|--------|
| **6.1** | Database Foundation | SQLite schema, WineRepository, migrate WineMatcher | ✅ Complete |
| **6.2** | Ingestion Core | DataSourceAdapter protocol, RatingNormalizer, pipeline | ✅ Complete |
| **6.3** | Kaggle Adapter | Config-driven CSV adapter for Kaggle 150K wines | ✅ Complete |
| **6.4** | Entity Resolution | Fuzzy + phonetic matching, deduplication | ✅ Complete |
| **6.5** | Performance & Polish | Index tuning, cache warming, CLI tool | ✅ Complete |

### Data Sources (Priority Order)

| Source | Records | Rating Scale | Priority |
|--------|---------|--------------|----------|
| **Kaggle Wine Reviews** | 150K | 80-100 → 1-5 | P0 (required) |
| Vivino | TBD | 1-5 | P1 (nice to have) |
| X-Wines | TBD | 1-5 | P2 (future) |

### Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite over Postgres | Single file, ships with Python, sufficient for 500K wines |
| Config-driven adapters | No code changes for new CSV sources (YAML mappings) |
| Tier-aligned normalization | Wine Enthusiast 90 = "outstanding" → ~4.0, not 2.5 |
| Repository pattern | Clean separation, easy to test, swappable sources |

### Gate 6 Criteria

- [x] SQLite database created with FTS5 full-text search
- [x] WineMatcher refactored to use WineRepository
- [x] Kaggle 150K wines ingested successfully (191K total from multiple sources)
- [x] Rating scale normalized (80-100 → 1-5) with tier alignment
- [x] Entity resolution handles duplicates (71% merge rate)
- [x] Wine lookup latency < 50ms for 150K wines (verified: 40.88ms avg)
- [x] Scan endpoint returns accurate matches for common wines
- [x] All existing tests pass (111 tests passed)

**Exit Condition:** ✅ Database contains 191K wines, scan endpoint accurately identifies common wines.

---

## Phase 7: TestFlight & App Store

**Goal:** Ship to App Store with full wine database.

### TestFlight Tasks

| Task | Status | Notes |
|------|--------|-------|
| App icon design | ⏳ TODO | Wine glass + rating badge concept |
| Launch screen | ⏳ TODO | Simple, minimal |
| Crash reporting (Crashlytics) | ⏳ TODO | Optional but recommended |
| TestFlight build uploaded | ⏳ TODO | - |
| Internal beta (5-10 testers) | ⏳ TODO | Team/friends |
| External beta (20-50 testers) | ⏳ TODO | Wine enthusiasts |
| Fix critical bugs from beta | ⏳ TODO | - |
| Verify crash rate < 1% | ⏳ TODO | - |

### App Store Tasks

| Task | Status | Notes |
|------|--------|-------|
| App name + subtitle | ⏳ TODO | "Wine Shelf Scanner" / "Instant Ratings" |
| App description | ⏳ TODO | 4000 chars max |
| Screenshots (6.7", 6.5", 5.5") | ⏳ TODO | 4-5 per size |
| Privacy policy URL | ⏳ TODO | Required |
| Category: Food & Drink | ⏳ TODO | - |
| Submit for review | ⏳ TODO | - |

### Gate 7 Criteria

- [ ] TestFlight build approved
- [ ] 5+ internal testers completed testing
- [ ] 20+ external testers completed testing
- [ ] Crash rate < 1% over 7 days
- [ ] All critical bugs fixed
- [ ] Wine recognition accuracy > 80% on test photos
- [ ] App Store metadata complete
- [ ] Screenshots uploaded
- [ ] Privacy policy published
- [ ] **App Store submission APPROVED**

**Exit Condition:** App is LIVE on App Store.

---

## Deferred (Post-MVP)

| Feature | Status | Notes |
|---------|--------|-------|
| Paywall (3-5 free scans) | Spec exists | In CLAUDE.md |
| Scan counter | Not started | LocalStorage |
| Live AR scanning | Out of scope | Explicitly excluded |
| User accounts | Out of scope | Not needed |
| Social features | Out of scope | Not needed |

---

## Critical Path Summary

```
Deploy → Refactor → Ingest 150K wines → TestFlight → App Store
   ↓         ↓              ↓               ↓            ↓
 Gate 4   Gate 5      ✅ Gate 6         Gate 7      LAUNCH
```

**Blockers (in order):**
1. Cloud Run deployment (blocking everything)
2. Global singleton fix (blocking clean code)
3. ~~Kaggle wine ingestion~~ ✅ Complete (191K wines)
4. TestFlight approval (blocking beta testing)
5. App Store approval (blocking launch)

---

## Test Summary

| Module | Test File | Count |
|--------|-----------|-------|
| Backend - Scan API | `tests/test_scan.py` | 8 |
| Backend - Wine Matcher | `tests/test_wine_matcher.py` | 9 |
| Backend - OCR Processor | `tests/test_ocr_processor.py` | 9 |
| Backend - LLM Normalizer | `tests/test_llm_normalizer.py` | 31 |
| Backend - Recognition Pipeline | `tests/test_recognition_pipeline.py` | 17 |
| Backend - Performance | `tests/test_performance.py` | 13 |
| Backend - E2E Scan | `tests/test_scan_e2e.py` | 24 |
| **Backend Total** | | **111** |
| iOS - OverlayMath | `OverlayMathTests.swift` | 26 |
| iOS - ScanResponse | `ScanResponseTests.swift` | 18 |

---

## Quick Commands

```bash
# Deploy backend
cd backend && ./deploy.sh YOUR_PROJECT_ID

# Run backend locally
cd backend && source venv/bin/activate && uvicorn main:app --reload

# Run backend tests
cd backend && pytest tests/ -v

# Open iOS project
open ios/WineShelfScanner.xcodeproj

# Run iOS tests
cd ios && xcodebuild test -scheme WineShelfScanner -destination 'platform=iOS Simulator,name=iPhone 15'
```

---

## Verification Steps

**Phase 4 (MVP):**
```bash
# Backend health check
curl https://YOUR-CLOUD-RUN-URL/health

# iOS → Backend connection
# Open Xcode, run on device, take photo of wine shelf
```

**Phase 5 (Refactor):**
```bash
# Run all backend tests
cd backend && pytest tests/ -v

# Verify no global state
grep -r "global " backend/app/
```

**Phase 6 (Data Ingestion):** ✅ Verified 2026-01-31
```bash
# All tests pass (111 tests)
cd backend && pytest tests/ -v

# Benchmark results: 191K wines, 40.88ms avg fuzzy lookup
python scripts/ingest.py --benchmark
```

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Technical specification (API contract, overlay math, non-goals) |
| `PRD.md` | Product vision (success criteria, what to cut) |
| `README.md` | Quick start guide for developers |
| `docs/DATA_INGESTION_PLAN.md` | Detailed spec for Phase 6 database expansion |
| `docs/REPOSITORY_ARCHITECTURE.md` | Database abstraction design |
