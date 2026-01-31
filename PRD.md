# Product Requirements Document (PRD)
## Wine Shelf Scanner (MVP v1.1)

---

## Product Name
Wine Shelf Scanner (working title)

---

## One-Line Pitch
Point your phone at a wine shelf and instantly see which bottles are worth buying — with ratings overlaid directly on the bottles.

---

## Problem Statement
Casual wine buyers face **decision paralysis** in liquor stores:

- Hundreds of unfamiliar labels
- Ratings scattered across apps and websites
- Existing wine apps require manual search or label-by-label scanning

This creates high cognitive load at the exact moment users want speed and confidence.

---

## Target User
**Casual Wine Drinker**
- Buys wine 1–4× per month
- Not a wine expert
- Wants the best option for the price *available on the shelf*
- Will not manually search or read long reviews in-store

### Explicit Non-Targets
- Sommeliers
- Collectors
- Cellar management users
- Vineyard discovery enthusiasts

---

## Core Insight
> Matching bottles from a list is too much work.

The UX must:
- Eliminate label-to-list matching
- Show quality **in place**, directly on the shelf image

**Overlaying ratings on top of bottles is the core differentiator.**

---

## MVP Scope (Strict)

### Primary User Flow
1. User opens iOS app
2. Takes **one photo** of a wine shelf
3. Image is uploaded to backend
4. Backend:
   - Detects bottles
   - Performs OCR on labels
   - Normalizes wine names
   - Matches against ratings database
5. App receives:
   - Bottle bounding boxes
   - Normalized wine names
   - Ratings + confidence
6. App overlays **star ratings directly on the bottles**

That’s the entire MVP.

---

## Explicit Non-Goals (MVP)
- Live AR scanning
- Continuous video processing
- User accounts or profiles
- Social features
- Recommendations
- Price comparison
- Purchase links
- Real-time web scraping

If it doesn’t support *choosing a bottle faster*, it’s out.

---

## UX Requirements

### Overlay Design
- Rating badge floats **on the bottle**
- Star scale: **1–5 stars** (optionally visualized as 1–10 later)
- Readable at arm’s length
- High contrast
- Subtle drop shadow
- Anchored to upper third of bottle

### Visual Priority Rules
- Top 3 highest-rated bottles:
  - Slight glow or thicker outline
  - Slightly larger rating badge
- Other detected bottles remain visible but de-emphasized

No hiding. No shaming low ratings.

---

## Interaction Model

### Tap Interaction (Important)
- Tap rating badge or bottle → **lightweight detail sheet**

Detail sheet shows:
- Wine name
- Star rating
- Confidence label:
  - “Widely rated” (high confidence)
  - “Limited data” (medium confidence)
- Optional short summary (future)

Rules:
- No long scrolling
- Swipe down to dismiss
- Must feel instant and non-disruptive

This tap provides reassurance, not research.

---

## Failure & Fallback UX

### Partial Detection
- Show overlays for detected bottles
- Toast message:
  > “Some bottles couldn’t be recognized”

### Full Detection Failure
- Automatically fall back to **list view**:
  - Detected wine names
  - Ratings
  - Sorted by rating descending

User must never hit a dead end.

---

## Technical Architecture (MVP)

### Client (iOS)
- SwiftUI
- Native camera capture
- Single photo capture only
- Static image upload
- Overlay rendering using bounding boxes

### Backend
- FastAPI (Python)

### Vision System (Required)
**Google Cloud Vision API**
- TEXT_DETECTION (OCR)
- OBJECT_LOCALIZATION (bottles)

Google Vision is responsible for *all* image understanding.

---

## OCR Normalization & Matching Strategy

### Raw OCR Reality
OCR output is noisy:
- Fragmented
- Orderless
- Mixed with marketing text
- Mixed with bottle size, vintage, region

### Normalization Goals
- Remove years (e.g. 2018, 2021)
- Remove sizes (750ml, 1L)
- Remove filler / marketing phrases
- Canonical format:
Producer + Wine Name


### AI Assist (Optional, Server-Side)
A language model (e.g. Claude) may be used **only** for:
- Cleaning OCR output
- Collapsing fragments into a canonical wine name
- Resolving near-matches
- Producing a confidence score

Important:
- The LLM does **not** perform vision
- The LLM is optional and swappable
- The system must work with heuristic-only normalization

---

## Overlay Placement Heuristics

Initial rules:
- Anchor overlay to **upper-center third** of bottle
- Use bounding box center-mass

Adjustments:
- If overlay overlaps label text → shift upward
- If bottle is partially occluded → anchor to largest visible region

These heuristics must be tunable without model retraining.

---

## Performance Targets
- End-to-end scan: **≤ 4 seconds**
- Confidence threshold for display: configurable
- Battery friendly (single image processing)

---

## Monetization (Deferred)

MVP:
- Free
- No login
- No paywall interruption

Planned:
- X free scans
- Subscription unlocks unlimited scans

Rules:
- Never block the first successful scan
- Paywall appears only *after* value is delivered

---

## Deliverables (MVP Phase)

1. SwiftUI app:
 - Camera capture
 - Static test image support
 - Overlay rendering
 - Detail sheet
2. Mock backend payloads
3. Overlay placement logic
4. OCR normalization prompts
5. TestFlight readiness checklist

---

## Success Metric
> A casual user can walk into a store, take one photo, and confidently choose a bottle in under **10 seconds**.

If this works, the product has legs.