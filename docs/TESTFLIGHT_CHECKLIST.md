# TestFlight & App Store Checklist

**Last Updated:** January 31, 2026

This document tracks all deliverables for Phase 7 (TestFlight & App Store).

---

## Deliverables Status

### App Icon

| Item | Status | Notes |
|------|--------|-------|
| Assets.xcassets structure | ✅ Delivered | `ios/WineShelfScanner/Resources/Assets.xcassets/` |
| AppIcon.appiconset/Contents.json | ✅ Delivered | All 18 required sizes defined |
| AccentColor (wine burgundy) | ✅ Delivered | #722F37 light, #8B4049 dark |
| **Actual icon images** | ⏳ TODO | See design spec below |

**Icon Design Spec:**
- Concept: Wine glass silhouette with star rating badge
- Primary color: Wine burgundy (#722F37)
- Badge color: Gold (#FFD700) or white
- Background: Gradient or solid wine color
- Style: Minimalist, recognizable at 29pt

**Required image files** (place in `AppIcon.appiconset/`):
```
icon-20.png      (20x20)
icon-20@2x.png   (40x40)
icon-20@3x.png   (60x60)
icon-20@2x-ipad.png (40x40)
icon-29.png      (29x29)
icon-29@2x.png   (58x58)
icon-29@3x.png   (87x87)
icon-29@2x-ipad.png (58x58)
icon-40.png      (40x40)
icon-40@2x.png   (80x80)
icon-40@3x.png   (120x120)
icon-40@2x-ipad.png (80x80)
icon-60@2x.png   (120x120)
icon-60@3x.png   (180x180)
icon-76.png      (76x76)
icon-76@2x.png   (152x152)
icon-83.5@2x.png (167x167)
icon-1024.png    (1024x1024)  ← Design this first, export others
```

**Quick option:** Use https://appicon.co - upload 1024x1024, get all sizes

---

### Launch Screen

| Item | Status | Notes |
|------|--------|-------|
| LaunchBackground color | ✅ Delivered | Wine burgundy in Assets.xcassets |
| Auto-generated launch screen | ✅ Ready | Uses `UILaunchScreen_Generation = YES` |
| Custom LaunchScreen.storyboard | ⏳ Optional | Only if you want centered logo |

**Current behavior:** iOS auto-generates a solid color launch screen using your AccentColor. This is simple and fast.

**To customize (optional):**
1. Create `LaunchScreen.storyboard` in Xcode
2. Add ImageView with app icon centered
3. Set background to LaunchBackground color
4. Update project to use storyboard instead of auto-generation

---

### Privacy & Compliance

| Item | Status | Notes |
|------|--------|-------|
| PrivacyInfo.xcprivacy | ✅ Delivered | iOS 17+ privacy manifest |
| NSCameraUsageDescription | ✅ Already set | In project.pbxproj |
| NSPhotoLibraryUsageDescription | ✅ Already set | In project.pbxproj |
| Privacy policy URL | ⏳ TODO | Required for App Store |

**Privacy policy options:**
- Free generator: https://www.freeprivacypolicy.com
- Host on GitHub Pages, Notion, or your website
- Must cover: camera usage, photo access, no data collection

---

### App Store Connect Setup

| Item | Status | Notes |
|------|--------|-------|
| Apple Developer account | ⏳ Verify | $99/year enrollment |
| App record created | ⏳ TODO | appstoreconnect.apple.com |
| Bundle ID registered | ⏳ TODO | `com.wineshelfscanner.app` |
| Development team set | ⏳ TODO | Update `DEVELOPMENT_TEAM` in project |

**Steps:**
1. Go to https://appstoreconnect.apple.com
2. My Apps → + → New App
3. Enter: Name, Primary Language, Bundle ID, SKU

---

### TestFlight Build

| Item | Status | Notes |
|------|--------|-------|
| Version number | ✅ Set | 1.0 (MARKETING_VERSION) |
| Build number | ✅ Set | 1 (CURRENT_PROJECT_VERSION) |
| Archive created | ⏳ TODO | Product → Archive in Xcode |
| Uploaded to App Store Connect | ⏳ TODO | Organizer → Distribute |
| Internal testing enabled | ⏳ TODO | Add testers in ASC |

**Test information (required for TestFlight):**
```
What to Test:
- Take a photo of a wine shelf
- Verify rating badges appear on recognized bottles
- Tap a badge to see wine details
- Check fallback list for unrecognized bottles

Contact Email: [your email]

Beta App Description:
Wine Shelf Scanner helps you instantly see ratings for wines
on store shelves. Point, shoot, and choose confidently.
```

---

### App Store Metadata

| Item | Status | Notes |
|------|--------|-------|
| App name | ⏳ TODO | "Wine Shelf Scanner" (30 chars max) |
| Subtitle | ⏳ TODO | "Instant Wine Ratings" (30 chars max) |
| Description | ⏳ TODO | See draft below |
| Keywords | ⏳ TODO | wine,ratings,scanner,sommelier,reviews |
| Screenshots | ⏳ TODO | 4-5 per device size |
| Category | ⏳ TODO | Food & Drink |
| Age rating | ⏳ TODO | 17+ (alcohol reference) |

**App Description Draft:**
```
Stop guessing which wine to buy.

Wine Shelf Scanner instantly shows you ratings for every bottle
on the shelf. Just take a photo and see which wines are worth
your money.

HOW IT WORKS
1. Point your camera at any wine shelf
2. Take a photo
3. See ratings appear on each bottle
4. Tap any bottle for details

FEATURES
• Instant wine recognition from 190,000+ wines
• Ratings from trusted wine reviewers
• Works offline after initial scan
• No account required

Choose confidently in seconds, not minutes.
```

**Screenshot requirements:**
- 6.7" (iPhone 15 Pro Max): 1290 x 2796 px
- 6.5" (iPhone 14 Plus): 1284 x 2778 px
- 5.5" (iPhone 8 Plus): 1242 x 2208 px

---

## Pre-Upload Checklist

Before archiving for TestFlight:

- [ ] Set `DEVELOPMENT_TEAM` in project.pbxproj
- [ ] Add app icon images to AppIcon.appiconset
- [ ] Test on real device (not just simulator)
- [ ] Verify camera permissions work
- [ ] Verify API connection to Cloud Run
- [ ] No placeholder text or "Lorem ipsum"
- [ ] No crash on launch
- [ ] Remove any debug logging (print statements)

---

## Commands

```bash
# Open project in Xcode
open /Users/juliancarlin/dev/wine-shelf-scanner/ios/WineShelfScanner.xcodeproj

# Build for testing
xcodebuild -scheme WineShelfScanner -destination 'platform=iOS Simulator,name=iPhone 15'

# Create archive (do this in Xcode GUI for signing)
# Product → Archive

# Run tests
xcodebuild test -scheme WineShelfScanner -destination 'platform=iOS Simulator,name=iPhone 15'
```

---

## Next Steps (Ordered)

1. **Create app icon** (1024x1024) → export all sizes
2. **Register bundle ID** in Apple Developer portal
3. **Create app record** in App Store Connect
4. **Set DEVELOPMENT_TEAM** in Xcode
5. **Archive and upload** to TestFlight
6. **Add internal testers** (5-10 people)
7. **Test and fix bugs**
8. **Submit for external beta** review
9. **Expand to 20-50 testers**
10. **Prepare App Store metadata**
11. **Submit for App Store review**

---

## Resources

- [App Store Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [Human Interface Guidelines - App Icons](https://developer.apple.com/design/human-interface-guidelines/app-icons)
- [TestFlight Documentation](https://developer.apple.com/testflight/)
- [App Icon Generator](https://appicon.co)
- [Privacy Policy Generator](https://www.freeprivacypolicy.com)
