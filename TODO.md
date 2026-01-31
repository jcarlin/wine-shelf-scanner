# Wine Shelf Scanner - Implementation Checklist

## Backend

- [x] FastAPI project setup (`main.py`, `requirements.txt`)
- [x] `/scan` endpoint (receives image, returns JSON)
- [ ] Google Vision integration (`TEXT_DETECTION`)
- [ ] Google Vision integration (`OBJECT_LOCALIZATION`)
- [ ] OCR text grouping by spatial proximity to bottle bbox
- [ ] Text normalization (remove years, sizes, marketing)
- [ ] LLM integration interface (swappable/removable)
- [ ] Mock ratings database
- [x] Response schema validation (match API contract exactly)

## iOS - Core

- [x] Xcode project setup (SwiftUI, iOS 16+)
- [ ] Camera view (photo capture)
- [x] Static test image support
- [x] API client for `/scan` endpoint
- [x] Image upload handling

## iOS - Overlay System

- [x] OverlayMath utility (`SwiftUI/WineShelfScanner/Utils/OverlayMath.swift`)
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

## Documentation

- [x] CLAUDE.md (consolidated technical spec)
- [x] TODO.md (this file)
- [x] PRD.md (canonical product requirements)
- [x] PLAN.md (development plan)
