# Year/Vintage Support — Findings & Scope

## Problem Statement

Wine ratings are often vintage-specific. A 2019 Caymus Cabernet and a 2021 Caymus Cabernet can differ significantly in quality. The current system treats all vintages of the same wine as a single entity with an aggregated rating, which means users may see inaccurate ratings for the specific bottle on the shelf in front of them.

---

## Current State: Year Is Actively Discarded

The system has **nine separate locations** that strip vintage information. This is not an oversight — it was a deliberate design choice to simplify wine matching by treating all vintages as one canonical entry.

### Where year data is removed

| Location | File | What happens |
|----------|------|-------------|
| OCR text cleaning | `backend/app/services/ocr_processor.py:14,78` | `_YEAR_PATTERN = re.compile(r'\b(19\|20)\d{2}\b')` strips years from OCR text |
| OCR filler words | `ocr_processor.py:182` | The word "vintage" itself is in `FILLER_WORDS` |
| OCR normalization | `ocr_processor.py:452` | `self.YEAR_PATTERN.sub('', result)` in `_normalize_text()` |
| Vivino adapter | `ingestion/adapters/vivino_global_adapter.py:180` | `_clean_wine_name()` strips year suffixes |
| Config adapter | `ingestion/adapters/config_adapter.py:45-49` | Three regex transforms: `remove_vintage_suffix`, `remove_vintage_prefix`, `remove_vintage_anywhere` |
| Ingestion configs | `configs/vivino_global.yaml`, `kaggle_reviews.yaml`, `kaggle_130k.yaml` | All apply vintage removal transforms |
| Entity resolution | `ingestion/entities.py:218` | `_normalize_for_key()` strips `\b(19\|20)\d{2}\b` for deduplication |
| LLM normalizer | `services/llm_normalizer.py:300` | Prompt instructs LLM: "REMOVE: vintage years" |
| LLM validation | `services/llm_normalizer.py:190` | Year differences treated as "acceptable" for matching |

### Where year data partially exists

| Location | Status | Notes |
|----------|--------|-------|
| `wine_reviews.vintage` column | Schema exists, sparsely populated | Individual reviews can store vintage |
| Flash Names LLM prompt | Requests vintage in name | "producer + wine + vintage if visible" but result is normalized away |
| Vivino scraper CSV output | Year column written | `scrape_vivino.py:411` saves Year to CSV, but ingestion discards it |
| ReviewItem API model | `vintage: Optional[str]` field | Only in `/wines/{id}/reviews` response, not in scan results |

### Where year data is completely absent

| Location | Notes |
|----------|-------|
| `wines` table schema | No `vintage`/`year` column — only `canonical_name` + single `rating` |
| `WineResult` model | No year field in scan response (`backend/app/models/response.py:52-76`) |
| `FallbackWine` model | No year field |
| `llm_ratings_cache` table | No vintage column |
| iOS `WineResult` struct | No year field |
| Next.js `WineResult` type | No year field (`nextjs/lib/types.ts`) |
| API contract (CLAUDE.md) | Year not part of the contract |

---

## What We're Losing

### Source data HAS vintage-specific ratings

The Vivino scraper (`backend/scripts/scrape_vivino.py:400-411`) pulls per-vintage data from Vivino's API:

```
Vivino API → year=2020, rating=4.5
Vivino API → year=2019, rating=4.3
Vivino API → year=2018, rating=4.1
```

During ingestion, all three get merged into one canonical entry: `"Caymus Cabernet Sauvignon"` with an averaged rating of ~4.3.

### Real-world impact

For wines where vintage matters significantly (Bordeaux, Burgundy, Barolo, vintage Champagne), the aggregated rating can be misleading. A user standing in front of a 2015 Barolo (great vintage, 4.6 rating) sees the same rating as if they were looking at a 2014 (mediocre vintage, 3.9 rating).

For wines where vintage matters less (most everyday wines, NV Champagne, multi-vintage blends), the current behavior is fine.

---

## Scope of Change

Adding year support touches every layer of the stack. Below is an exhaustive list of what would need to change.

### Layer 1: Database Schema

**New migration required.** Two approaches:

**Option A — Separate vintage table (recommended)**
```sql
CREATE TABLE wine_vintages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id INTEGER NOT NULL,
    year INTEGER,                    -- NULL for NV wines
    rating REAL,                     -- vintage-specific rating
    rating_count INTEGER DEFAULT 0,  -- number of ratings for this vintage
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE,
    UNIQUE(wine_id, year)
);
```
- Keeps current `wines` table and its aggregated rating intact (backward compatible)
- Allows multiple vintages per wine
- `year IS NULL` represents NV (non-vintage) wines
- The `wines.rating` remains the overall/default rating

**Option B — Add year to wines table**
- Would require composite unique key on `(canonical_name, year)`
- Breaks the current 1:1 assumption between canonical name and wine entry
- More disruptive, less recommended

### Layer 2: Data Ingestion

| File | Change |
|------|--------|
| `ingestion/protocols.py` | Add `year: Optional[int]` to `RawWineRecord` |
| `ingestion/entities.py` | Track vintage-specific ratings in `CanonicalWine`; stop stripping years from dedup keys (or dedup by name only but track per-vintage ratings) |
| `ingestion/pipeline.py` | Write vintage data to new `wine_vintages` table |
| `ingestion/adapters/vivino_global_adapter.py` | Pass through year from CSV instead of stripping |
| `ingestion/adapters/config_adapter.py` | Add `year` field mapping support |
| `configs/vivino_global.yaml` | Map Year column, remove `remove_vintage_suffix` transform |
| `configs/kaggle_reviews.yaml` | Extract year before stripping from name |
| `configs/kaggle_130k.yaml` | Extract year before stripping from name |

**Key decision:** Wine names in the `wines` table should likely remain vintage-free (canonical). The year goes into the `wine_vintages` table, not into the name.

### Layer 3: OCR Pipeline

| File | Change |
|------|--------|
| `services/ocr_processor.py` | **Extract** year into a separate field instead of stripping it. `_normalize_text()` should return both `normalized_name` (year-free) and `detected_year: Optional[int]` |
| `BottleText` dataclass | Add `detected_year: Optional[int]` field |

The year should still be removed from the name used for DB matching (matching should remain vintage-agnostic), but the extracted year needs to be preserved and passed forward.

### Layer 4: Wine Matching

| File | Change |
|------|--------|
| `services/wine_matcher.py` | After matching a canonical wine, look up vintage-specific rating from `wine_vintages` if a year was detected by OCR |
| `services/wine_repository.py` | Add `get_vintage_rating(wine_id, year)` method |

**Matching strategy stays the same** — match on canonical name first, then refine the rating with vintage-specific data if available.

### Layer 5: LLM / Flash Names Pipeline

| File | Change |
|------|--------|
| `services/flash_names_pipeline.py` | Parse year from LLM response as a separate field (it's already requested in the prompt but currently ignored). Add `year` to the LLM result dataclass |
| `services/llm_normalizer.py` | Update prompts to return year as a separate JSON field rather than embedded in the name. Update response parsing |
| `services/recognition_pipeline.py` | Pass detected year through the pipeline |

### Layer 6: API Response

| File | Change |
|------|--------|
| `models/response.py` | Add `year: Optional[int] = None` to `WineResult` and `FallbackWine` |
| `CLAUDE.md` | Update API contract |

**API contract change:**
```json
{
  "wine_name": "Caymus Cabernet Sauvignon",
  "year": 2021,
  "rating": 4.5,
  "confidence": 0.92,
  "bbox": { ... }
}
```

`year` is nullable — `null` means vintage was not detected or wine is NV.

### Layer 7: Frontend (iOS)

| File | Change |
|------|--------|
| `Models/ScanResponse.swift` | Add `year: Int?` to `WineResult` |
| `Views/Components/WineDetailSheet.swift` | Display year alongside wine name |
| `Views/Components/RatingBadge.swift` | No change needed (badge shows rating only) |

### Layer 8: Frontend (Next.js)

| File | Change |
|------|--------|
| `nextjs/lib/types.ts` | Add `year?: number \| null` to `WineResult` |
| `nextjs/components/WineDetailModal.tsx` | Display year alongside wine name |
| `nextjs/components/RatingBadge.tsx` | No change needed |

### Layer 9: Caching

| File | Change |
|------|--------|
| `services/llm_rating_cache.py` | Add `year` column to `llm_ratings_cache` table (migration). Cache lookups should check (name, year) when year is available |

### Layer 10: Tests

| Area | Change |
|------|--------|
| `tests/test_ocr_processor.py` | Update year extraction tests — year should be extracted, not discarded |
| `tests/accuracy/test_accuracy.py` | `test_remove_vintage` and `test_vintage_difference` need updating |
| All mock fixtures | Add `year` field to mock scan responses |
| E2E tests | Verify year displays in frontend |

---

## Rating Fallback Logic

When a scan detects a year:

1. Look up the canonical wine in `wines` table (vintage-free match)
2. Check `wine_vintages` for a vintage-specific rating
3. If vintage-specific rating exists → use it
4. If not → fall back to the canonical (aggregated) rating
5. In the response, always return the detected `year` even if we used the aggregated rating

This means the feature is **incrementally valuable** — even with sparse vintage data, we improve accuracy for wines where we do have it, and change nothing for wines where we don't.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| API contract change breaks existing clients | High | `year` is nullable/optional — existing clients ignore it. Add field, don't remove any |
| DB migration on production | Medium | Additive migration (new table), no changes to existing tables |
| Matching accuracy regression | Low | Matching stays vintage-agnostic; year only refines the rating post-match |
| Data sparsity (not all wines have per-vintage ratings) | Medium | Fallback to aggregated rating. User sees no difference for wines without vintage data |
| OCR year detection false positives | Low | Years in wine context (on labels) are almost always vintage. Rare edge case: addresses, phone numbers — already handled by spatial proximity to bottle |
| Increased DB size | Low | `wine_vintages` table adds ~5-10 rows per wine for popular wines |

---

## What This Does NOT Include

Per the project's non-goals:
- No vintage recommendation engine ("try the 2019 instead")
- No historical vintage charts or year comparisons
- No vintage-specific reviews aggregation (reviews stay as-is)
- No price-by-vintage data

The change is scoped to: **detect year → show year → use vintage-specific rating when available**.

---

## Estimated Scope

- **Database:** 1 new migration, 1 new table
- **Backend files to modify:** ~15 files
- **Frontend files to modify:** ~4 files (2 iOS, 2 Next.js)
- **Test files to modify:** ~5-8 files
- **New tests to add:** ~10-15 test cases
- **No new external dependencies**
- **No new API endpoints** (just a new field on existing responses)
