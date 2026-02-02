# Wine Shelf Scanner - Ralph Loop Completion Protocol

## Mission

Bring Wine Shelf Scanner to **100% functional** status through iterative improvement.
Each iteration: measure → analyze → fix → verify → expand corpus → repeat.

**Success Criterion (from CLAUDE.md):**
> "A casual user can walk into a store, take one photo, and confidently choose a bottle in under 10 seconds."

---

## Completion Criteria (HARD TARGETS)

You are DONE when ALL of these are met:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Precision | ≥ 85% | `python scripts/accuracy_report.py --corpus test-images/corpus/labels/` |
| Recall | ≥ 80% | Same command |
| F1 Score | ≥ 82% | Same command |
| Backend Tests | 100% pass | `pytest tests/ -v` |
| Feature Gaps | 0 critical | See checklist below |

When targets are met, output exactly:
<promise>WINE SCANNER COMPLETE - Precision: X%, Recall: Y%, F1: Z%</promise>

---

## Current State (Context)

**What's Working:**
- 192K wines in SQLite database (FTS5 indexed)
- Tiered recognition: Vision API → fuzzy match → LLM fallback
- iOS app fully implements overlay UX (confidence opacity, top-3 emphasis)
- 152 backend tests passing
- Feedback collection endpoint built

**Critical Gaps to Close:**

| Gap | Severity | File(s) |
|-----|----------|---------|
| HEIC image support (backend scripts) | HIGH | `config.py`, `requirements.txt` |
| Confidence calculation too conservative | HIGH | `recognition_pipeline.py` |
| No Vision API retry logic | MEDIUM | `vision.py` |
| Static fallback list (same 4 wines) | MEDIUM | `scan.py` |
| Feedback loop not integrated | LOW | `wine_matcher.py` |
| Unknown baseline accuracy | HIGH | Need to run evaluation |

---

## Iteration Protocol

### Each Iteration:

**1. MEASURE** - Establish baseline
```bash
cd backend
python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/ --analyze-failures --verbose
```

Record: Precision, Recall, F1, top failure category

**2. ANALYZE** - Identify root cause
Look at failure categories:
- `ocr_error` → Fix `ocr_processor.py` (text grouping, proximity threshold)
- `matching_error` → Fix `wine_matcher.py` (FTS query, fuzzy thresholds)
- `threshold_high` → Lower thresholds in `config.py`
- `threshold_low` → Raise thresholds or improve matching specificity
- `not_in_db` → Add wine aliases or improve LLM fallback

**3. FIX** - Make ONE focused improvement
- Address the highest-impact failure category
- Make the minimal change that fixes it
- Aggressive changes allowed (refactor, add deps, change architecture)

**4. VERIFY** - Confirm improvement
```bash
pytest tests/ -v  # All tests must pass
python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/
```

Metrics should improve (or at least not regress)

**5. EXPAND** - Add to test corpus
If corpus has < 25 images with ground truth:
```bash
# Generate stubs for images without ground truth
python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/ --generate-stubs
```
Then manually verify/correct the generated JSON files.

**6. COMMIT** - Save progress
```bash
git add -A && git commit -m "Ralph iteration N: [what you fixed]"
```

**7. LOOP OR EXIT**
- If targets NOT met → Go to step 1
- If targets MET → Output promise tag

---

## Feature Gaps Checklist

Close these as you iterate. Check off when complete:

### Critical (Must Fix)
- [ ] **HEIC Support**: Add `pillow-heif` to requirements.txt, update `ALLOWED_CONTENT_TYPES` in config.py
- [ ] **Confidence Calculation**: Replace `min(bottle_conf, match_conf)` with weighted formula
- [ ] **Baseline Accuracy**: Run initial evaluation to establish where we are

### High Priority
- [ ] **Vision API Retry**: Add retry decorator with exponential backoff to `vision.py`
- [ ] **Dynamic Fallback**: Generate fallback list from top-rated wines in database (not hardcoded)
- [ ] **Ground Truth Corpus**: Expand to 25+ images with verified annotations

### Medium Priority
- [ ] **Feedback Integration**: Use corrections table to boost/penalize matches
- [ ] **LLM Cache Population**: Pre-populate cache for common wines
- [ ] **Threshold Tuning**: Optimize confidence thresholds based on failure analysis

---

## Key Files Reference

**Accuracy Scripts:**
```
backend/scripts/accuracy_report.py    # Main evaluation CLI
backend/scripts/iteration_loop.py     # Automated iteration framework
backend/tests/accuracy/metrics.py     # Precision/Recall/F1 calculations
```

**Pipeline Code:**
```
backend/app/routes/scan.py            # /scan endpoint, fallback generation
backend/app/services/recognition_pipeline.py  # Main pipeline orchestration
backend/app/services/wine_matcher.py  # FTS + fuzzy matching
backend/app/services/ocr_processor.py # Text grouping from Vision API
backend/app/services/vision.py        # Google Vision API client
backend/app/config.py                 # All thresholds and constants
```

**Test Corpus:**
```
test-images/corpus/labels/            # Individual wine label images
test-images/corpus/ground_truth/      # JSON annotations (wine_name, expected_rating)
test-images/corpus/shelves/           # Full shelf images
test-images/*.HEIC                    # HEIC test files (need support)
test-images/images.cv/                # Additional bottle images (100+)
```

**Database:**
```
backend/app/data/wines.db             # SQLite with 192K wines
backend/app/data/schema.sql           # Schema reference
```

---

## Ground Truth Format

Each image needs a corresponding JSON in `ground_truth/`:

```json
{
  "image_file": "100062.jpeg",
  "wines": [
    {
      "wine_name": "Kendall-Jackson Vintner's Reserve Chardonnay",
      "expected_rating": 4.2,
      "rating_tolerance": 0.5,
      "notes": ""
    }
  ],
  "total_visible_bottles": 1,
  "notes": ""
}
```

---

## Aggressive Changes Allowed

You have permission to:
- **Refactor** the matching pipeline architecture
- **Change** the confidence calculation formula
- **Add** new Python dependencies (update requirements.txt)
- **Modify** database schema (add tables, indexes, columns)
- **Restructure** code modules if it improves accuracy
- **Tune** any threshold or weight in config.py
- **Add** new wine aliases or data to the database

Do NOT:
- Change the API contract (response schema in CLAUDE.md)
- Remove existing tests (add new ones instead)
- Break the iOS app (it depends on the API contract)

---

## Commands Cheat Sheet

```bash
# Run accuracy evaluation
cd backend && python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/ --analyze-failures -v

# Quick test (10 images)
python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/ --max-images 10

# Generate ground truth stubs
python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/ --generate-stubs

# Run all backend tests
pytest tests/ -v

# Start dev server (for manual testing)
uvicorn main:app --reload

# Check iteration history
python scripts/iteration_loop.py --status --corpus ../test-images/corpus/labels/
```

---

## Example Iteration

**Iteration 1:**
1. Run `accuracy_report.py` → Precision: 0.62, Recall: 0.58, F1: 0.60
2. Top failure: `threshold_high` (35%) - good matches being filtered
3. Fix: Lower `FUZZY_CONFIDENCE_THRESHOLD` from 0.7 to 0.65 in config.py
4. Verify: Tests pass, new metrics: Precision: 0.68, Recall: 0.65, F1: 0.66
5. Commit: "Ralph iteration 1: Lower fuzzy confidence threshold"

**Iteration 2:**
1. Run evaluation → Precision: 0.68, Recall: 0.65, F1: 0.66
2. Top failure: `not_in_db` (28%) - wines missing from database
3. Fix: Add aliases for common wine variations
4. Verify: Tests pass, Precision: 0.72, Recall: 0.70, F1: 0.71
5. Commit: "Ralph iteration 2: Add common wine aliases"

...continue until targets met...

---

## Final Verification

Before outputting the promise tag:

1. **Accuracy Check:**
```bash
python scripts/accuracy_report.py --corpus ../test-images/corpus/labels/ --analyze-failures
```
Confirm: Precision ≥85%, Recall ≥80%, F1 ≥82%

2. **Test Suite:**
```bash
pytest tests/ -v
```
Confirm: All tests pass

3. **Feature Gaps:**
Review checklist - all Critical items must be checked

4. **Manual Smoke Test:**
```bash
uvicorn main:app --reload
# Upload a test image via /docs Swagger UI
# Verify reasonable results returned
```

Then output:
<promise>WINE SCANNER COMPLETE - Precision: X%, Recall: Y%, F1: Z%</promise>
