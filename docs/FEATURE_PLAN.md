# Feature Implementation Plan
## Features 1, 2, 5, 7

**Created:** February 4, 2026

These four features share a philosophy: **own the moment at the shelf, not the wine lifecycle.** Every change makes the scan result more decisive, not more informational. None require accounts, backends at rest, or social infrastructure.

---

## Feature Gate Architecture

All four features ship behind feature flags. Each flag defaults to `false` (off) in production until the feature is verified, then flipped to `true`. This allows incremental rollout, A/B testing, and instant kill-switch if something breaks.

### Flag Definitions

| Flag Key | Controls | Default |
|----------|----------|---------|
| `feature_wine_memory` | Feature 1: Device-local liked/disliked persistence + overlay indicators | `false` |
| `feature_shelf_ranking` | Feature 2: "#1 of 8" rank numbers on badges and detail sheet | `false` |
| `feature_safe_pick` | Feature 5: "Crowd favorite" badge on qualifying wines | `false` |
| `feature_pairings` | Feature 7: Food pairing one-liner in detail sheet | `false` |

### Backend: `pydantic-settings` BaseSettings

The project already depends on `pydantic-settings 2.1.0` (in `requirements.txt`). This is the [FastAPI-recommended approach](https://fastapi.tiangolo.com/advanced/settings/) for typed, validated, environment-variable-backed configuration.

```python
# backend/app/feature_flags.py
from pydantic_settings import BaseSettings
from functools import lru_cache


class FeatureFlags(BaseSettings):
    """Feature flags backed by environment variables.

    Toggle via env vars (e.g., FEATURE_PAIRINGS=true).
    All flags default to False (off) until explicitly enabled.
    """
    feature_wine_memory: bool = False
    feature_shelf_ranking: bool = False
    feature_safe_pick: bool = False
    feature_pairings: bool = False

    model_config = {
        "env_prefix": "",           # No prefix — flag name IS the env var
        "case_sensitive": False,    # FEATURE_PAIRINGS=true works
    }


@lru_cache()
def get_feature_flags() -> FeatureFlags:
    """Cached singleton. Use FastAPI Depends() for injection."""
    return FeatureFlags()
```

**Usage in routes (FastAPI dependency injection):**
```python
from fastapi import Depends
from app.feature_flags import FeatureFlags, get_feature_flags

@router.post("/scan")
async def scan_image(
    image: UploadFile,
    flags: FeatureFlags = Depends(get_feature_flags),
):
    # ... existing pipeline ...

    if flags.feature_pairings:
        for result in results:
            result.pairing = pairing_service.get_pairing(result.varietal, result.wine_type)

    if flags.feature_safe_pick:
        for result in results:
            result.is_safe_pick = compute_safe_pick(result)
```

**Why this works:**
- `pydantic-settings` is already a dependency — no new packages
- Validates types (rejects `FEATURE_PAIRINGS=maybe` with a clear error)
- FastAPI `Depends()` injection — standard pattern, testable (override in tests)
- `@lru_cache` ensures single parse per process lifetime
- `.env` file support built in (via `python-dotenv`, also already installed)
- Add to `.env.example` for discoverability

### iOS: UserDefaults + FeatureFlags struct

iOS has zero external dependencies. Apple's standard pattern for runtime feature flags is a dedicated type backed by `UserDefaults`. This is the approach used by most production iOS apps that don't use a remote config service.

```swift
// ios/WineShelfScanner/Config/FeatureFlags.swift
import Foundation

/// Feature flags backed by UserDefaults.
///
/// Defaults are compiled in. Override at runtime via:
/// - Debug settings UI (dev builds)
/// - UserDefaults.standard.set(true, forKey: "feature_wine_memory")
///
/// Upgrade path: Replace UserDefaults reads with Firebase Remote Config
/// or LaunchDarkly SDK calls when remote toggling is needed.
struct FeatureFlags {
    static let shared = FeatureFlags()

    private let defaults = UserDefaults.standard

    // Compiled defaults — flip to true when feature is ready
    private let compiledDefaults: [String: Bool] = [
        "feature_wine_memory": false,
        "feature_shelf_ranking": false,
        "feature_safe_pick": false,
        "feature_pairings": false,
    ]

    var wineMemory: Bool {
        flagValue("feature_wine_memory")
    }

    var shelfRanking: Bool {
        flagValue("feature_shelf_ranking")
    }

    var safePick: Bool {
        flagValue("feature_safe_pick")
    }

    var pairings: Bool {
        flagValue("feature_pairings")
    }

    /// Returns UserDefaults override if set, otherwise compiled default.
    private func flagValue(_ key: String) -> Bool {
        if defaults.object(forKey: key) != nil {
            return defaults.bool(forKey: key)
        }
        return compiledDefaults[key] ?? false
    }

    /// Override a flag at runtime (debug builds).
    func setOverride(_ key: String, value: Bool) {
        defaults.set(value, forKey: key)
    }

    /// Remove runtime override, revert to compiled default.
    func removeOverride(_ key: String) {
        defaults.removeObject(forKey: key)
    }
}
```

**Usage:**
```swift
// In OverlayContainerView.swift
if FeatureFlags.shared.shelfRanking {
    // compute and show rank numbers
}

// In WineDetailSheet.swift
if FeatureFlags.shared.pairings, let pairing = wine.pairing {
    PairingSection(pairing: pairing)
}
```

**Why UserDefaults and not a library:**
- iOS currently has zero external dependencies — intentional design choice
- UserDefaults is Apple's own API for key-value persistence
- The struct pattern above is the same pattern used by apps like Signal and Wikipedia iOS
- Clear upgrade path: swap `flagValue()` internals with Firebase Remote Config or LaunchDarkly SDK when remote toggling is needed (no call sites change)
- Toggleable from debug settings UI or Xcode console during development

**Upgrade path (when remote config is needed):**
- Add `firebase-ios-sdk` via SPM (Swift Package Manager)
- Replace `flagValue()` body with `RemoteConfig.remoteConfig().configValue(forKey: key).boolValue`
- No changes to call sites — the `FeatureFlags.shared.pairings` API stays the same

### Expo: `expo-constants` + React Context Provider

Expo's managed SDK provides `expo-constants` for build-time configuration and React Context for runtime flag access. This is the [Expo-recommended pattern](https://docs.expo.dev/versions/latest/sdk/constants/) for app configuration.

```typescript
// expo/lib/feature-flags.tsx
import React, { createContext, useContext, useMemo } from 'react';
import Constants from 'expo-constants';

interface FeatureFlagValues {
  wineMemory: boolean;
  shelfRanking: boolean;
  safePick: boolean;
  pairings: boolean;
}

// Build-time defaults from app.json extra config
const defaults: FeatureFlagValues = {
  wineMemory: Constants.expoConfig?.extra?.featureWineMemory ?? false,
  shelfRanking: Constants.expoConfig?.extra?.featureShelfRanking ?? false,
  safePick: Constants.expoConfig?.extra?.featureSafePick ?? false,
  pairings: Constants.expoConfig?.extra?.featurePairings ?? false,
};

const FeatureFlagContext = createContext<FeatureFlagValues>(defaults);

export function FeatureFlagProvider({ children }: { children: React.ReactNode }) {
  const flags = useMemo(() => defaults, []);
  return (
    <FeatureFlagContext.Provider value={flags}>
      {children}
    </FeatureFlagContext.Provider>
  );
}

export function useFeatureFlags(): FeatureFlagValues {
  return useContext(FeatureFlagContext);
}
```

**Build-time config in `app.json`:**
```json
{
  "expo": {
    "extra": {
      "featureWineMemory": false,
      "featureShelfRanking": false,
      "featureSafePick": false,
      "featurePairings": false
    }
  }
}
```

**Usage in components:**
```typescript
// In OverlayContainer.tsx
const { shelfRanking } = useFeatureFlags();

const rankings = useMemo(() => {
  if (!shelfRanking) return new Map();
  // ... compute ranks
}, [shelfRanking, visibleWines]);
```

**Why this approach:**
- `expo-constants` is built into every Expo project — no new dependency
- `Constants.expoConfig.extra` is Expo's documented mechanism for custom app config
- React Context is the standard React pattern for cross-component state
- Flags can be overridden per EAS build profile (dev vs staging vs production)
- Upgrade path: swap the context provider internals with Statsig React SDK, PostHog, or LaunchDarkly React Native SDK

### Next.js: Environment Variables + Flags Module

Next.js has built-in support for `NEXT_PUBLIC_*` environment variables, which are the [documented approach](https://nextjs.org/docs/app/building-your-application/configuring/environment-variables) for client-side configuration. Since the app deploys to Vercel, flags can be toggled per-environment in the Vercel dashboard.

```typescript
// nextjs/lib/feature-flags.ts

interface FeatureFlagValues {
  wineMemory: boolean;
  shelfRanking: boolean;
  safePick: boolean;
  pairings: boolean;
}

function envBool(key: string): boolean {
  return process.env[key]?.toLowerCase() === 'true';
}

export const featureFlags: FeatureFlagValues = {
  wineMemory: envBool('NEXT_PUBLIC_FEATURE_WINE_MEMORY'),
  shelfRanking: envBool('NEXT_PUBLIC_FEATURE_SHELF_RANKING'),
  safePick: envBool('NEXT_PUBLIC_FEATURE_SAFE_PICK'),
  pairings: envBool('NEXT_PUBLIC_FEATURE_PAIRINGS'),
};

// React hook for component use (re-exports for consistency with Expo)
export function useFeatureFlags(): FeatureFlagValues {
  return featureFlags;
}
```

**Vercel dashboard env vars:**
```
NEXT_PUBLIC_FEATURE_WINE_MEMORY=false
NEXT_PUBLIC_FEATURE_SHELF_RANKING=false
NEXT_PUBLIC_FEATURE_SAFE_PICK=false
NEXT_PUBLIC_FEATURE_PAIRINGS=false
```

**Usage:**
```typescript
// In OverlayContainer.tsx
import { useFeatureFlags } from '@/lib/feature-flags';

const { shelfRanking, safePick } = useFeatureFlags();
```

**Why this approach:**
- `NEXT_PUBLIC_*` env vars are Next.js's built-in feature config mechanism — zero dependencies
- Vercel dashboard provides per-environment overrides (preview, production, development)
- Flags are inlined at build time by Next.js — no runtime overhead
- Upgrade path: replace with [`@vercel/flags`](https://vercel.com/docs/workflow-collaboration/feature-flags) SDK for edge-based evaluation, percentage rollouts, and Vercel toolbar integration

### Flag Lifecycle

```
1. Feature in development  → flag = false (code exists, UI hidden)
2. Feature ready for QA     → flag = true in dev/staging env only
3. Feature verified         → flag = true in production
4. Feature stable (2+ weeks)→ remove flag, inline the code
```

Flags are temporary scaffolding. Once a feature is stable, delete the flag and its conditionals. Dead flags are technical debt.

### Testing with Flags

**Backend:** Override via FastAPI dependency injection in tests:
```python
def test_scan_with_pairings(client):
    app.dependency_overrides[get_feature_flags] = lambda: FeatureFlags(feature_pairings=True)
    response = client.post("/scan", ...)
    assert response.json()["results"][0]["pairing"] is not None
```

**iOS:** Set UserDefaults before test:
```swift
func testShelfRanking() {
    UserDefaults.standard.set(true, forKey: "feature_shelf_ranking")
    // ... test rank display
    UserDefaults.standard.removeObject(forKey: "feature_shelf_ranking")
}
```

**Expo/Next.js:** Mock the context or module:
```typescript
jest.mock('@/lib/feature-flags', () => ({
  useFeatureFlags: () => ({ shelfRanking: true, pairings: true }),
}));
```

---

## Feature 1: Wine Memory ("Not This One Again")

### What it is
Device-local thumbs-up/thumbs-down that persists across scans. On future scans, previously rejected wines show a red X on the overlay. Previously liked wines show a small heart. Zero effort, no reviews to write, no account.

### What exists today
- **iOS** has thumbs-up/down buttons in `WineDetailSheet.swift` (lines 286-316) + a correction text field
- **Expo** and **Next.js** have NO feedback UI in their detail modals
- Backend has a `corrections` table (`schema.sql:143-152`) that stores feedback with `device_id` — but this is for backend learning, not user-facing memory
- **No local persistence** exists on any frontend (no UserDefaults, no AsyncStorage, no localStorage)

### What changes

**Backend: Nothing.** This is entirely client-side. The existing `corrections` endpoint continues to feed backend accuracy. Wine memory is a separate, local concern.

**All frontends: New local storage layer + overlay modifications.** All gated behind `FeatureFlags.wineMemory` / `useFeatureFlags().wineMemory`.

#### Data Model (same across platforms)
```
WineMemoryEntry {
  wine_name: string          // canonical name from scan result
  sentiment: "liked" | "disliked"
  timestamp: ISO 8601 date
}
```

Storage: dictionary keyed by lowercase `wine_name`.

#### iOS Changes
| File | Change |
|------|--------|
| **New: `WineMemoryStore.swift`** | Singleton wrapping `UserDefaults` (key: `"wine_memory"`). Methods: `save(wineName, sentiment)`, `get(wineName) -> sentiment?`, `clear(wineName)`, `allEntries() -> [WineMemoryEntry]`. Serialized as JSON. |
| `WineDetailSheet.swift` | Existing thumbs-up/down should ALSO write to `WineMemoryStore` (currently only calls `FeedbackService`). Show "You liked this" / "You didn't like this" banner if wine is in memory when sheet opens. Add undo button. |
| `RatingBadge.swift` | New optional `userSentiment: String?` parameter. When `"disliked"`: overlay a small red X icon (SF Symbol `xmark.circle.fill`) at top-right of badge. When `"liked"`: small green heart (`heart.fill`). |
| `OverlayContainerView.swift` | Look up each wine in `WineMemoryStore` before rendering badge. Pass sentiment to `RatingBadge`. |
| `ScanResponse.swift` | No change — memory is overlaid client-side on top of API data. |

#### Expo Changes
| File | Change |
|------|--------|
| **New: `hooks/useWineMemory.ts`** | Hook wrapping `AsyncStorage` (key: `"wine_memory"`). Returns `{ save, get, clear, entries }`. Loads once on mount, updates in-memory cache on writes. |
| **New: Feedback UI in `WineDetailModal.tsx`** | Port iOS feedback buttons (thumbs-up/down + correction field). Currently Expo has no feedback UI at all. Wire to both `useWineMemory` (local) and API feedback endpoint (server). |
| `RatingBadge.tsx` | Add `userSentiment?: "liked" \| "disliked"` prop. Render small indicator icon. |
| `OverlayContainer.tsx` | Consume `useWineMemory` hook. Look up each wine, pass sentiment to badge. |

#### Next.js Changes
| File | Change |
|------|--------|
| **New: `hooks/useWineMemory.ts`** | Hook wrapping `localStorage` (key: `"wine_memory"`). Same interface as Expo hook. SSR-safe (check `typeof window`). |
| **New: Feedback UI in `WineDetailModal.tsx`** | Same as Expo — port feedback buttons. Currently Next.js has no feedback UI. |
| `RatingBadge` component | Same `userSentiment` prop treatment. |
| `OverlayContainer.tsx` | Same lookup + pass pattern. |

#### Visual Design
```
Normal badge:     [★ 4.2]
Disliked wine:    [★ 4.2] ✕  (red X icon, top-right of badge, 12px)
Liked wine:       [★ 4.2] ♥  (green heart icon, top-right, 12px)
```

The X/heart is small enough not to obscure the rating but visible enough to register at a glance. The sentiment indicator appears on the overlay — the user doesn't need to tap to see it.

#### Edge Cases
- **Same wine, different scan:** Match by canonical `wine_name` (already normalized by backend).
- **Storage limits:** Cap at 500 entries. LRU eviction (oldest timestamp). 500 wines is more than anyone will rate.
- **Memory conflicts:** If user liked a wine, then dislikes it, latest write wins.
- **Fallback list:** Memory indicators also appear in fallback list view (text-based: strikethrough for disliked, heart icon for liked).

#### What this does NOT include
- Cloud sync across devices (post-MVP if accounts ever happen)
- Wine history/journal view (separate feature)
- Smart suggestions based on memory (recommendation engine — explicitly out of scope)

---

## Feature 2: Shelf-Relative Ranking

### What it is
Every visible bottle gets a rank: "#1 of 8 on this shelf." The #1 bottle gets a "Best on shelf" label. This reframes abstract ratings (4.2 means nothing in isolation) into actionable comparison (this is the best thing in front of you right now).

### What exists today
- Top-3 emphasis: yellow glow border + larger badge (52x28 vs 44x24)
- Bottles sorted by rating in the response
- No rank number shown anywhere — not on badge, not in detail sheet
- The data to compute rank is already present (the list of visible results + ratings)

### What changes

**Backend: Nothing.** The rank is derived entirely from the scan response on the client. The API already returns all visible wines with ratings. Computing rank server-side would be redundant and couples display logic to the API.

**All frontends: Rank computation + display in badge and detail sheet.** Gated behind `FeatureFlags.shelfRanking` / `useFeatureFlags().shelfRanking`. When flag is off, existing top-3 glow logic continues unchanged.

#### Rank Computation (same logic, all platforms)
```
1. Filter to visible wines (confidence >= 0.45 AND rating != null)
2. Sort by rating descending
3. Assign rank 1..N
4. Ties: same rank (e.g., two wines at 4.2 both get #3)
5. Store: shelfRank and shelfTotal per wine
```

This computation already partially exists — top-3 is calculated the same way. The rank is a natural extension.

#### iOS Changes
| File | Change |
|------|--------|
| `OverlayContainerView.swift` | Compute `shelfRank` and `shelfTotal` for each wine (extend existing top-3 sort). Pass to `RatingBadge`. |
| `RatingBadge.swift` | New optional `shelfRank: Int?` param. Show small rank number below rating text: "#1" in gold for rank 1, "#2" in silver for rank 2, white for others. Only show if `shelfTotal >= 3` (ranking 2 bottles is pointless). |
| `WineDetailSheet.swift` | Add rank context line below rating: "Ranked #2 of 8 on this shelf" or "Best on this shelf" for #1. Subtle, secondary text. |
| `ScanResponse.swift` | Add computed helper: `func shelfRanking() -> [(wine: WineResult, rank: Int)]` |

#### Expo Changes
| File | Change |
|------|--------|
| `OverlayContainer.tsx` | Compute rankings in `useMemo` (extend existing `topThreeIds` calculation). Pass `shelfRank` and `shelfTotal` to `RatingBadge`. |
| `RatingBadge.tsx` | New `shelfRank?: number` prop. Small rank text below rating. |
| `WineDetailModal.tsx` | Accept and display rank context. |

#### Next.js Changes
| File | Change |
|------|--------|
| `OverlayContainer.tsx` | Same as Expo — compute ranks, pass down. |
| `RatingBadge` | Same prop addition. |
| `WineDetailModal.tsx` | Same rank display. |

#### Visual Design
```
Top-3 badge (rank 1):    [★ 4.6]     (existing glow)
                          #1          (gold, 10px, below badge)

Top-3 badge (rank 2):    [★ 4.4]     (existing glow)
                          #2          (silver, 10px)

Normal badge (rank 5):   [★ 3.8]
                          #5          (white, 9px, subtle)

Only 2 bottles:          [★ 4.1]     (no rank shown — too few to rank)
```

#### Detail Sheet Rank Display
```
#1 wine:   "🏆 Best on this shelf"              (gold accent)
#2-3:      "Ranked #2 of 8 on this shelf"       (secondary text)
#4+:       "Ranked #5 of 8 on this shelf"       (secondary text, muted)
```

#### Edge Cases
- **Only 1-2 bottles detected:** Don't show rank numbers (nothing meaningful to compare).
- **Ties in rating:** Share rank. "#2 of 8" for both, next wine skips to #4.
- **Wines without ratings:** Exclude from ranking. They don't get rank numbers.
- **Fallback list:** Show rank in list form too: "#1", "#2" etc. as prefix.

#### Interaction with Top-3 Emphasis
Rank numbers complement but don't replace top-3 glow. The glow is a visual cue; the number is informational. Both serve the same goal: make relative quality obvious at a glance.

---

## Feature 5: "Safe Pick" Badge

### What it is
A badge on select wines that says "Crowd favorite" — meaning this wine is broadly liked, broadly available, and hard to go wrong with. It answers the #1 anxiety of casual buyers: "Will this be embarrassing?"

### What exists today
- `rating` field (1-5) — always present for DB matches
- `review_count: Optional[int]` in the API model — but **not stored in the DB.** The `wines` table has no `review_count` column. Currently only populated by Claude Vision fallback estimates.
- `confidence` field — match confidence, not popularity
- `varietal` and `wine_type` — present in DB for most wines

### The data gap
The critical missing piece is `review_count`. Without knowing how many people rated a wine, we can't distinguish between "4.3 from 50,000 reviews" (genuine crowd favorite) and "4.3 from 12 reviews" (niche wine that happens to score well).

**Two approaches:**

#### Approach A: Add review_count to ingestion (recommended)
The Kaggle wine reviews dataset (`raw-data/`) likely contains review counts or can be derived from the number of reviews per wine. If so:

| File | Change |
|------|--------|
| `schema.sql` | Add `review_count INTEGER` column to `wines` table |
| `wine_repository.py` | Return `review_count` in queries |
| Kaggle adapter config | Map review count column |
| `ingest.py` | Populate review_count during ingestion |
| Migration script | `ALTER TABLE wines ADD COLUMN review_count INTEGER` for existing DB |

This is a one-time data pipeline change. Once review_count is in the DB, Safe Pick becomes a simple derived flag.

#### Approach B: Heuristic without review_count (fallback)
If review count data isn't available, use proxies:
- Rating >= 4.0 (broadly liked)
- Varietal is common (Cabernet Sauvignon, Chardonnay, Pinot Noir, Merlot, Sauvignon Blanc, etc.)
- Region is well-known (Napa, Bordeaux, Barossa, Marlborough, Rioja, etc.)
- Source is database (not LLM-estimated)
- Confidence >= 0.85

This is weaker but still useful. A 4.2 Napa Cabernet is objectively a safe pick for a dinner party even without review count data.

### Safe Pick Criteria (with review_count)
```python
is_safe_pick = (
    rating >= 4.0
    and review_count >= 500
    and confidence >= 0.85
    and rating_source == "database"   # we trust the rating
)
```

### Safe Pick Criteria (heuristic fallback)
```python
SAFE_VARIETALS = {"cabernet sauvignon", "merlot", "pinot noir", "chardonnay",
                  "sauvignon blanc", "pinot grigio", "syrah", "malbec",
                  "riesling", "tempranillo", "zinfandel", "rosé"}

is_safe_pick = (
    rating >= 4.0
    and confidence >= 0.85
    and rating_source == "database"
    and (varietal or "").lower() in SAFE_VARIETALS
)
```

### What changes

Gated behind `feature_safe_pick` flag (backend) / `FeatureFlags.safePick` (iOS) / `useFeatureFlags().safePick` (Expo/Next.js). When flag is off, `is_safe_pick` is never computed and remains `null` — frontends skip all safe pick rendering.

**Backend:**
| File | Change |
|------|--------|
| `response.py` | Add `is_safe_pick: Optional[bool] = Field(None)` to `WineResult` |
| `config.py` | Add `SAFE_PICK_MIN_RATING = 4.0`, `SAFE_PICK_MIN_REVIEWS = 500` |
| `routes/scan.py` | Compute `is_safe_pick` only when `flags.feature_safe_pick` is True. Simple boolean derived from existing data. |
| `schema.sql` | (Approach A) Add `review_count` column |
| `wine_repository.py` | (Approach A) Include `review_count` in query results |

**iOS:**
| File | Change |
|------|--------|
| `ScanResponse.swift` | Add `isSafePick: Bool?` to `WineResult` decode |
| `RatingBadge.swift` | New optional `isSafePick: Bool` param. When true: small shield icon (SF Symbol `checkmark.shield.fill`) next to rating, in green. |
| `WineDetailSheet.swift` | When `isSafePick`: show "Crowd favorite — hard to go wrong" label below confidence. Green accent color. |

**Expo:**
| File | Change |
|------|--------|
| `lib/types.ts` | Add `is_safe_pick?: boolean` to `WineResult` |
| `RatingBadge.tsx` | Shield icon when safe pick. |
| `WineDetailModal.tsx` | "Crowd favorite" label. |

**Next.js:**
| File | Change |
|------|--------|
| `lib/types.ts` | Add `is_safe_pick?: boolean` to `WineResult` |
| Same component changes as Expo. |

#### Visual Design
```
Badge (safe pick):    [★ 4.2 🛡]     (small green shield, 10px, right of rating)

Detail sheet:
  ┌──────────────────────────┐
  │  ★★★★☆  4.2              │
  │  12.5K reviews            │
  │  ✅ Crowd favorite        │  ← new line, green accent
  │  "Hard to go wrong"       │
  └──────────────────────────┘
```

The shield is small and doesn't compete with the rating for attention. It's a reassurance signal, not a primary data point.

#### Edge Cases
- **Multiple safe picks on one shelf:** Fine. Show the badge on all of them. The user sees which cluster of bottles are reliable choices.
- **No safe picks on shelf:** Don't show anything. No empty state needed — absence of the badge is its own signal.
- **LLM-estimated ratings:** Never mark as safe pick. We can't vouch for a rating we made up.
- **Safe pick + disliked (Feature 1):** Both indicators show. User sees "this is popular but you didn't like it" — useful information.

#### Data Investigation Needed
Before implementing, check:
```bash
# Does Kaggle data have review counts?
head -1 raw-data/kaggle/*.csv | grep -i "review\|count\|num"

# How many wines have review_count populated via Vision?
sqlite3 backend/app/data/wines.db "SELECT COUNT(*) FROM wines"
```

---

## Feature 7: "Pair With" One-Liner

### What it is
One short food pairing line per wine: "Goes with grilled lamb" or "Pizza wine." Shown in the detail sheet. Answers the second-most-common question after "is it good?" — "what do I eat with it?"

### What exists today
- `blurb: Optional[str]` field exists in `WineResult` model — used for general wine description
- Claude Vision already generates blurbs for vision-identified wines
- DB-matched wines rarely have blurbs (the field exists but isn't populated from ingestion)
- LLM infrastructure exists (Claude Haiku / Gemini) — already used for name normalization

### Design decision: Separate field vs. extending blurb

**Separate field (`pairing`)** is better because:
- Blurb = "what is this wine" (descriptive)
- Pairing = "what do I eat with it" (actionable)
- Different display treatment (icon, placement)
- Can be generated independently (rule-based for common varietals, LLM for others)

### What changes

Gated behind `feature_pairings` flag (backend) / `FeatureFlags.pairings` (iOS) / `useFeatureFlags().pairings` (Expo/Next.js). When flag is off, pairing service is never called and `pairing` remains `null`.

**Backend:**
| File | Change |
|------|--------|
| `response.py` | Add `pairing: Optional[str] = Field(None, description="Food pairing suggestion")` to `WineResult` |
| **New: `services/pairing.py`** | Pairing generation service. Two tiers: (1) Lookup table for common varietals, (2) LLM generation for uncommon wines. |
| `routes/scan.py` | Call pairing service only when `flags.feature_pairings` is True. |

#### Tier 1: Varietal Lookup Table (zero latency)
```python
VARIETAL_PAIRINGS = {
    "cabernet sauvignon": "Steak, lamb, aged cheese",
    "merlot": "Roast chicken, mushroom dishes, pasta",
    "pinot noir": "Salmon, duck, grilled vegetables",
    "chardonnay": "Lobster, creamy pasta, roast chicken",
    "sauvignon blanc": "Goat cheese, seafood, salads",
    "pinot grigio": "Light fish, sushi, antipasto",
    "riesling": "Thai food, spicy dishes, pork",
    "syrah": "BBQ ribs, stew, smoked meats",
    "malbec": "Grilled steak, empanadas, blue cheese",
    "tempranillo": "Tapas, chorizo, manchego",
    "zinfandel": "Pizza, burgers, BBQ",
    "sangiovese": "Pasta with red sauce, pizza, salami",
    "grenache": "Mediterranean dishes, roasted vegetables",
    "viognier": "Rich fish, apricot dishes, mild curry",
    "gewürztraminer": "Asian cuisine, foie gras, spicy food",
    "nebbiolo": "Truffle dishes, braised meat, risotto",
    "gamay": "Charcuterie, light chicken, picnic food",
    "chenin blanc": "Sushi, Thai food, fruit desserts",
    "muscadet": "Oysters, mussels, light seafood",
    "albariño": "Ceviche, grilled shrimp, paella",
    # Wine types as fallback
    "red": "Red meat, aged cheese, hearty dishes",
    "white": "Seafood, poultry, light dishes",
    "rosé": "Salads, light appetizers, grilled fish",
    "sparkling": "Appetizers, oysters, celebration food",
    "dessert": "Fruit tarts, blue cheese, dark chocolate",
}
```

This covers ~80% of wines in a 191K database. Zero latency, zero API cost.

#### Tier 2: LLM Generation (for uncovered wines)
For wines where varietal isn't in the lookup (or varietal is null):
- Batch with existing LLM calls (already happening for name normalization)
- Add to prompt: "Suggest one short food pairing (max 6 words)"
- Cache result in a new `wine_pairings` table or add column to `wines`

**Decision:** Start with Tier 1 only. It covers the vast majority of cases and adds zero latency. Tier 2 can be added later if users report missing pairings.

#### Pairing Service Implementation
```python
class PairingService:
    def get_pairing(self, varietal: str | None, wine_type: str | None) -> str | None:
        """Return food pairing string. Varietal lookup first, wine_type fallback."""
        if varietal and varietal.lower() in VARIETAL_PAIRINGS:
            return VARIETAL_PAIRINGS[varietal.lower()]
        if wine_type and wine_type.lower() in VARIETAL_PAIRINGS:
            return VARIETAL_PAIRINGS[wine_type.lower()]
        return None
```

No new dependencies. No API calls. No latency impact.

**iOS:**
| File | Change |
|------|--------|
| `ScanResponse.swift` | Add `pairing: String?` to `WineResult` |
| `WineDetailSheet.swift` | New section below blurb: fork icon + pairing text. Single line, italic, warm color. Only show if pairing is non-nil. |

**Expo:**
| File | Change |
|------|--------|
| `lib/types.ts` | Add `pairing?: string` to `WineResult` |
| `WineDetailModal.tsx` | Pairing section with fork emoji + text. |

**Next.js:**
| File | Change |
|------|--------|
| `lib/types.ts` | Add `pairing?: string` to `WineResult` |
| `WineDetailModal.tsx` | Same pairing display. |

#### Visual Design (Detail Sheet)
```
  ┌──────────────────────────┐
  │  ... existing content ... │
  │                           │
  │  🍴 Goes with             │  ← new section
  │  Steak, lamb, aged cheese │  ← warm color, italic
  │                           │
  │  ... review snippets ...  │
  └──────────────────────────┘
```

One line. No scrolling added. If pairing is null, section doesn't render.

#### Edge Cases
- **Unknown varietal:** Fall back to wine_type. If both null, don't show section.
- **Multiple varietals (blend):** Use first varietal listed, or wine_type fallback.
- **Pairing too long:** Cap at 40 characters in the lookup table. All entries above are under this.

---

## Implementation Order

These features have minimal dependencies on each other. Recommended order based on value and simplicity:

### Phase A: Shelf-Relative Ranking (Feature 2)
**Why first:** Zero backend changes. Pure frontend computation using data that already exists. Can be shipped to all three frontends independently. Immediately makes every scan more useful.

**Scope:** ~1 new computed property per frontend, badge modification, detail sheet line.

### Phase B: Pair-With One-Liner (Feature 7)
**Why second:** Backend change is tiny (one new service file, one new field). Tier 1 (lookup table) adds zero latency. High perceived value for a casual buyer — answers "what do I eat with this?" without any infrastructure cost.

**Scope:** 1 new backend service, 1 model field, detail sheet section across 3 frontends.

### Phase C: Safe Pick Badge (Feature 5)
**Why third:** Requires a data investigation first (do we have review counts?). If yes, straightforward. If no, the heuristic fallback is still useful but less confident. Backend model change + frontend badge addition.

**Scope:** 1 new model field, backend computation, badge/detail sheet across 3 frontends. Possible DB migration.

### Phase D: Wine Memory (Feature 1)
**Why last:** Largest surface area — requires new local storage on all 3 platforms, feedback UI parity (Expo and Next.js currently lack thumbs-up/down), overlay modifications, and edge case handling. Also the hardest to test (requires multiple scans to verify persistence).

**Scope:** New storage layer per platform, feedback UI on 2 platforms, badge overlay modification, detail sheet state awareness.

---

## API Contract Impact

| Field | Type | Feature | Breaking? |
|-------|------|---------|-----------|
| `is_safe_pick` | `Optional[bool]` | Feature 5 | No — additive, nullable |
| `pairing` | `Optional[str]` | Feature 7 | No — additive, nullable |
| `shelf_rank` | N/A | Feature 2 | No — computed client-side |
| Wine memory | N/A | Feature 1 | No — fully client-side |

**No breaking API changes.** All new fields are optional. Older clients ignore them. The API contract in CLAUDE.md remains valid — these are extensions to the already-optional metadata fields.

---

## Files Changed Summary

### New Files
| File | Feature | Purpose |
|------|---------|---------|
| `backend/app/feature_flags.py` | All | pydantic-settings feature flag class |
| `ios/.../Config/FeatureFlags.swift` | All | UserDefaults-backed feature flags |
| `expo/lib/feature-flags.tsx` | All | Expo Constants + React Context provider |
| `nextjs/lib/feature-flags.ts` | All | NEXT_PUBLIC env var flags module |
| `ios/.../WineMemoryStore.swift` | 1 | UserDefaults persistence |
| `expo/hooks/useWineMemory.ts` | 1 | AsyncStorage hook |
| `nextjs/hooks/useWineMemory.ts` | 1 | localStorage hook |
| `backend/app/services/pairing.py` | 7 | Varietal → pairing lookup |

### Modified Files
| File | Features |
|------|----------|
| `backend/app/models/response.py` | 5, 7 |
| `backend/app/config.py` | 5, 7 |
| `backend/app/routes/scan.py` | 5, 7 |
| `backend/app/data/schema.sql` | 5 (if adding review_count) |
| `ios/.../RatingBadge.swift` | 1, 2, 5 |
| `ios/.../WineDetailSheet.swift` | 1, 2, 5, 7 |
| `ios/.../OverlayContainerView.swift` | 1, 2 |
| `ios/.../ScanResponse.swift` | 2, 5, 7 |
| `expo/components/RatingBadge.tsx` | 1, 2, 5 |
| `expo/components/WineDetailModal.tsx` | 1, 2, 5, 7 |
| `expo/components/OverlayContainer.tsx` | 1, 2 |
| `expo/lib/types.ts` | 5, 7 |
| `nextjs/components/OverlayContainer.tsx` | 1, 2 |
| `nextjs/components/WineDetailModal.tsx` | 1, 2, 5, 7 |
| `nextjs/lib/types.ts` | 5, 7 |

### Test Coverage Needed
| Feature | Backend Tests | Frontend Tests |
|---------|--------------|----------------|
| 1 (Memory) | None (client-only) | Storage CRUD, persistence across hook remounts, LRU eviction at 500, sentiment override |
| 2 (Ranking) | None (client-only) | Rank computation with ties, rank hidden for <3 bottles, rank shown in badge |
| 5 (Safe Pick) | Safe pick criteria unit tests, edge cases (null review_count, LLM ratings excluded) | Badge renders shield icon, detail sheet shows label |
| 7 (Pairing) | Lookup coverage, unknown varietal fallback, null handling | Detail sheet renders pairing section, hides when null |
