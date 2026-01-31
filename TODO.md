# Wine Shelf Scanner - Implementation Checklist

## Backend

- [x] FastAPI project setup (`main.py`, `requirements.txt`)
- [x] `/scan` endpoint (receives image, returns JSON)
- [x] Google Vision integration (`TEXT_DETECTION`) - ready, needs credentials
- [x] Google Vision integration (`OBJECT_LOCALIZATION`) - ready, needs credentials
- [x] OCR text grouping by spatial proximity to bottle bbox
- [x] Text normalization (remove years, sizes, marketing)
- [ ] LLM integration interface (swappable/removable) - deferred
- [x] Mock ratings database (50+ wines)
- [x] Response schema validation (match API contract exactly)
- [x] Fuzzy wine matching with aliases
- [x] Dockerfile for Cloud Run
- [x] Deploy script (`deploy.sh`)

## iOS - Core

- [x] Xcode project setup (SwiftUI, iOS 16+)
- [x] Camera view (photo capture)
- [x] Photo library picker (for simulator testing)
- [x] Static test image support
- [x] API client for `/scan` endpoint
- [x] Image upload handling
- [x] Environment config (local/production URLs)

## iOS - Overlay System

- [x] OverlayMath utility (`ios/WineShelfScanner/Utils/OverlayMath.swift`)
- [x] Rating badge component
- [x] Confidence-based opacity (thresholds: 0.85, 0.65, 0.45)
- [x] Top-3 emphasis (glow, thicker stroke, larger badge)
- [x] Collision avoidance (shift upward, clamp to bounds)

## iOS - Detail Sheet

- [x] Tap gesture on rating badges
- [x] Modal sheet component (swipe to dismiss)
- [x] Wine name + star rating display
- [x] Confidence label logic ("Widely rated" / "Limited data")
- [x] Disable tap for confidence < 0.65

## iOS - Failure Handling

- [x] Toast for partial detection
- [x] Fallback list view (sorted by rating)
- [x] Loading states
- [x] Never dead-end the user

## iOS - Paywall (Deferred)

- [ ] Scan counter (local storage)
- [ ] Paywall trigger logic (after 3-5 free scans)
- [ ] Paywall UI (show after results render)

## Testing

- [x] Mock backend responses (JSON fixtures)
- [ ] Test images (varied shelf layouts)
- [ ] End-to-end flow test
- [x] Confidence threshold edge cases
- [x] OCR normalization tests (26 tests passing)
- [x] Wine matcher tests

## Deployment

- [x] Dockerfile
- [x] .dockerignore
- [x] cloudbuild.yaml
- [x] deploy.sh script
- [ ] Deploy to Cloud Run
- [ ] Update iOS app with production URL

## Documentation

- [x] CLAUDE.md (consolidated technical spec)
- [x] TODO.md (this file)
- [x] PRD.md (canonical product requirements)
- [x] PLAN.md (development plan)

## Next Steps

1. Deploy backend: `cd backend && ./deploy.sh YOUR_PROJECT_ID`
2. Update `Config.swift` with Cloud Run URL
3. Open Xcode: `open ios/WineShelfScanner.xcodeproj`
4. Run on device to test camera
5. TestFlight build (Phase 5)
