# Wine Shelf Scanner - Master Plan

## Executive Summary

Transform the Wine Shelf Scanner from MVP to a lean, profitable side project with passive income. Focus on sustainable revenue with minimal ongoing work.

**Current State:** Production MVP with 191K wines, <4s latency, iOS app ready for TestFlight.

**End State:** Polished iOS app generating $1-3K/month passive income with automated accuracy improvements.

**Philosophy:** Lean operation. iOS only. Ship when ready, not when rushed. Build systems that improve themselves.

---

## Part 1: Monetization Strategy

### Simple Freemium Model

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | 5 scans/month, full functionality |
| **Pro** | $3.99/mo or $19.99/yr | Unlimited scans |

**Why this works:**
- 5 scans = enough to validate value, not enough for weekly shopping
- $3.99 = impulse purchase, lower than coffee
- Annual discount = predictable revenue, better retention
- Simple = less support burden

**Revenue targets (realistic for side project):**
- Month 3: $500 MRR (125 Pro subscribers)
- Month 6: $1,500 MRR (375 subscribers)
- Month 12: $3,000 MRR (750 subscribers)

**Implementation:** Enable paywall after 2,000 downloads (prove value first)

### B2B: Deprioritized

B2B licensing requires sales cycles, custom integrations, and support. Not worth it for a side project unless someone approaches you organically. Keep the door open but don't pursue actively.

### What We Won't Do

- **Affiliate links** - Destroys trust, feels sleazy
- **Ads** - Kills the "fast" promise
- **Data selling** - Privacy nightmare
- **Multiple tiers** - Complexity without benefit
- **Active B2B sales** - Too much work for side project

---

## Part 2: Technical Roadmap (Side Project Pace)

### Phase A: The Feedback Flywheel (Weeks 1-6)

**Goal:** Build a self-improving system. Set it up once, let it run.

**Implementation:**
1. Simple feedback UI after scan results
   - Thumbs up/down per wine (one tap)
   - Optional "What's the correct wine?" text field
2. Store corrections in `corrections` table
3. Monthly batch job: review corrections, update database
4. Track 3 metrics only:
   - Match rate (% with confident match)
   - Correction rate (% marked wrong)
   - Weekly active users

**Files to modify:**
- `backend/app/routes/feedback.py` - New endpoint
- `backend/app/data/schema.sql` - `corrections` table
- iOS: Add feedback button to detail sheet

**Success metric:** <10% correction rate

### Phase B: Database Quality (Weeks 4-10)

**Goal:** Better coverage of common wines, not maximum wine count.

**Focus on:**
- Top 500 US wine retailers' inventory (most scanned wines)
- Fix entity resolution issues surfaced by user corrections
- Add "aliases" for common OCR misreads

**Skip for now:**
- Vivino API integration (legal complexity)
- Multiple rating sources (diminishing returns)
- International wines beyond major importers

**Files to modify:**
- `backend/app/data/aliases.json` - OCR correction mappings
- `backend/scripts/fix_corrections.py` - Batch correction processor

**Success metric:** 85% match rate on US wines

### Phase C: Custom Model (Future - If Needed)

**Status:** Deprioritized. Only pursue if:
- Vision API costs become prohibitive (>$500/month)
- Accuracy plateaus below 80% despite corrections
- You want to invest significant time

**When ready:**
- Collect 10K+ labeled images from production
- Fine-tune YOLO for wine label detection
- Deploy via Core ML for edge inference

**Not building now:** Too much work for marginal gains at this scale.

### Phase D: AR Overlay (Future - Phase 2)

**Status:** Cool feature, not core to value prop. Build after:
- 2,000+ paying subscribers
- Core accuracy is solid (85%+)
- You have time and energy

**When ready:**
- Single photo capture (no continuous recognition)
- ARKit anchoring for floating badges
- "View in AR" button after results

**Not building now:** Doesn't help users choose faster.

---

## Part 3: Go-to-Market Strategy (Steady Pace)

### Phase GTM-1: Quality Beta (Weeks 1-6)

**Goal:** Ship a polished product, not a rushed MVP.

**Actions:**
1. TestFlight internal beta (friends/family, 10-20 people)
2. Fix all critical bugs and UX issues
3. Polish the app icon, screenshots, description
4. TestFlight external beta (50 users from r/wine)
5. Collect feedback, iterate once more

**Recruitment (low effort):**
- Post on r/wine with genuine value (not spammy)
- Personal network who buys wine
- Wine-focused Discord servers

**Success criteria:**
- Zero crashes in beta
- 4.5+ internal rating
- "I'd pay for this" from 50%+ of testers

### Phase GTM-2: App Store Launch (Weeks 6-10)

**Goal:** Clean launch, organic discovery.

**Actions:**
1. App Store submission (free tier, no paywall yet)
2. ASO optimization:
   - Title: "Wine Scanner - Instant Ratings"
   - Keywords: wine scanner, wine ratings, sommelier, reviews
   - 5 polished screenshots
3. One Product Hunt post
4. One r/wine announcement (when approved)
5. Let organic growth work

**Skip for now:**
- Paid influencers
- Press outreach
- Paid advertising

**Success criteria:**
- 1,000 downloads in first 2 months
- 4.0+ App Store rating
- Organic growth trajectory

### Phase GTM-3: Monetization (Weeks 10-16)

**Goal:** Passive income stream.

**Trigger:** Enable paywall after 2,000 total downloads

**Implementation:**
1. Free tier: 5 scans/month
2. Pro: $3.99/mo or $19.99/yr
3. Paywall shown AFTER results (never before value)
4. Copy: "Unlimited instant ratings - Go Pro"

**Skip for now:**
- Referral programs (complexity)
- Discounts/promotions (devalues)
- Multiple tiers (confusion)

**Success criteria:**
- 3-5% conversion to Pro
- $500+ MRR by month 4
- Low churn (<10%/month)

### Phase GTM-4: Maintenance Mode (Week 16+)

**Goal:** Sustainable passive income with minimal work.

**Ongoing tasks (1-2 hours/week):**
- Review user feedback and corrections
- Monthly database quality fixes
- Respond to App Store reviews
- Monitor crash reports

**Growth levers (if you want more):**
- Seasonal pushes (holiday wine buying)
- App Store feature requests
- Word of mouth (the product IS the marketing)

**Revenue target:** $1-3K MRR with <5 hours/month maintenance

---

## Part 4: Competitive Position

### Why this can work as a side project

1. **Niche positioning**
   - Vivino is bloated (accounts, social, collection tracking)
   - You do ONE thing: fast in-store ratings
   - Simplicity is the feature

2. **Low marginal costs**
   - Cloud Run scales to zero when idle
   - Vision API: ~$1.50 per 1K scans
   - LLM fallback: ~$0.50 per 1K scans
   - Break-even: ~100 Pro subscribers

3. **Feedback flywheel**
   - Users improve accuracy for free
   - System gets better without your work
   - Compounding advantage over time

4. **No account = no support**
   - No password resets
   - No account issues
   - Minimal customer service

### Vivino comparison

| Feature | Wine Shelf Scanner | Vivino |
|---------|-------------------|--------|
| Scan speed | 2-4s | 5-10s |
| Account required | No | Yes |
| Primary use case | In-store decision | Collection tracking |
| Complexity | Minimal | Feature bloat |
| Price | $3.99/mo | Free + upsells |

**Positioning:** "The wine app that respects your time."

---

## Part 5: Implementation Order

### Phase 1: Polish & Beta (Weeks 1-6)

**Week 1-2:**
- [ ] Design app icon (1024x1024)
- [ ] Create App Store screenshots (5)
- [ ] Write App Store description
- [ ] Internal TestFlight (friends/family)

**Week 3-4:**
- [ ] Fix bugs from internal beta
- [ ] Add feedback button to detail sheet
- [ ] Create `/feedback` API endpoint
- [ ] External TestFlight (r/wine, 50 users)

**Week 5-6:**
- [ ] Fix bugs from external beta
- [ ] Verify crash rate <1%
- [ ] Privacy policy page
- [ ] App Store submission

### Phase 2: Launch & Learn (Weeks 6-12)

**Week 6-8:**
- [ ] App Store approval
- [ ] Product Hunt post
- [ ] r/wine announcement
- [ ] Monitor and respond to reviews

**Week 8-12:**
- [ ] Review user corrections weekly
- [ ] Fix top accuracy issues
- [ ] Add aliases for common OCR errors
- [ ] Reach 2,000 downloads

### Phase 3: Monetize (Weeks 12-20)

**Week 12-14:**
- [ ] Implement scan counter (local storage)
- [ ] Implement paywall UI
- [ ] RevenueCat integration (or StoreKit 2)
- [ ] Test purchase flow

**Week 14-20:**
- [ ] Enable paywall in production
- [ ] Monitor conversion rate
- [ ] A/B test paywall copy if needed
- [ ] Target: $500 MRR

### Phase 4: Maintenance (Ongoing)

**Monthly (2-4 hours):**
- Review and apply user corrections
- Check crash reports
- Respond to reviews
- Minor bug fixes

**Quarterly:**
- Database quality improvements
- iOS version updates
- Evaluate feature requests

---

## Part 6: Key Metrics (Keep It Simple)

Track monthly:

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Downloads | 500/month | Growth health |
| Weekly Active Users | 20% of total | Engagement |
| Correction rate | <10% | Accuracy proxy |
| Pro conversion | 3-5% | Revenue health |
| MRR | $1-3K | Sustainability |
| Crash rate | <1% | Quality |

**Don't over-optimize.** Check these monthly, not daily.

---

## Part 7: Risks (Realistic Assessment)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Low conversion rate | Medium | Medium | Test pricing, improve accuracy |
| Vivino improves speed | Low | Low | They're focused on social, not speed |
| Vision API costs grow | Low | Medium | Monitor; edge inference if needed |
| App Store rejection | Low | Low | No alcohol sales, just info |
| Burnout | Medium | High | Keep scope small, maintenance mode |

**Biggest actual risk:** Building too much. Keep it simple.

---

## Part 8: Files to Modify

### Phase 1 (Beta Polish)
- `ios/WineShelfScanner/Assets.xcassets/AppIcon.appiconset/` - App icon
- App Store Connect - Screenshots, description, metadata

### Phase 2 (Feedback System)
- `backend/app/routes/feedback.py` - New: POST `/feedback` endpoint
- `backend/app/data/schema.sql` - Add `corrections` table
- `ios/WineShelfScanner/Views/WineDetailSheet.swift` - Add feedback buttons

### Phase 3 (Monetization)
- `ios/WineShelfScanner/Services/ScanCounter.swift` - New: track scan count
- `ios/WineShelfScanner/Views/PaywallView.swift` - New: upgrade prompt
- `ios/WineShelfScanner/Services/PurchaseManager.swift` - New: StoreKit 2

### Future (If Needed)
- `backend/app/data/aliases.json` - OCR correction mappings
- `backend/scripts/apply_corrections.py` - Batch processor

---

## Summary

**Philosophy:** Lean side project generating passive income.

**Monetization:** Simple freemium at $3.99/mo, targeting $1-3K MRR.

**Technical focus:** Feedback flywheel for self-improving accuracy. No custom ML, no AR, no Android until there's a reason.

**Timeline:**
- Weeks 1-6: Polish and beta
- Weeks 6-12: Launch and learn
- Weeks 12-20: Monetize
- Ongoing: 2-4 hours/month maintenance

**Success criteria:** $1K+ MRR with <5 hours/month of work.

**The key insight:** The product is already 90% there. Don't over-engineer. Ship, learn from users, improve incrementally. Let the feedback flywheel do the work.

---

## Verification Plan

After implementation, verify success by:

1. **Beta phase:** Zero crashes, 50%+ of testers say "I'd pay for this"
2. **Launch phase:** 4.0+ App Store rating, organic download growth
3. **Monetization phase:** 3%+ Pro conversion, positive unit economics
4. **Maintenance phase:** <5 hours/month, stable or growing MRR
