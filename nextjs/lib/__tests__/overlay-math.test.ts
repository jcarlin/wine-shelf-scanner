import {
  anchorPoint,
  opacity,
  isVisible,
  isTappable,
  confidenceLabel,
  badgeSize,
  adjustedAnchorPoint,
  cornerBrackets,
  VISIBILITY_THRESHOLD,
  TAPPABLE_THRESHOLD,
  HIGH_CONFIDENCE_THRESHOLD,
  BASE_BADGE_SIZE,
  TOP_THREE_BADGE_SIZE,
} from '../overlay-math';

describe('overlay-math', () => {
  describe('constants', () => {
    it('should have correct threshold values', () => {
      expect(VISIBILITY_THRESHOLD).toBe(0.45);
      expect(TAPPABLE_THRESHOLD).toBe(0.65);
      expect(HIGH_CONFIDENCE_THRESHOLD).toBe(0.85);
    });

    it('should have correct badge sizes', () => {
      expect(BASE_BADGE_SIZE).toEqual({ width: 44, height: 24 });
      expect(TOP_THREE_BADGE_SIZE).toEqual({ width: 52, height: 28 });
    });
  });

  describe('anchorPoint', () => {
    it('should return center horizontally, 25% from top vertically', () => {
      const bbox = { x: 0.2, y: 0.4, width: 0.1, height: 0.3 };
      const container = { width: 100, height: 100 };

      const result = anchorPoint(bbox, container);

      // x = (0.2 + 0.1/2) * 100 = 25
      // y = (0.4 + 0.3*0.25) * 100 = 47.5
      expect(result.x).toBe(25);
      expect(result.y).toBe(47.5);
    });

    it('should scale correctly with different container sizes', () => {
      const bbox = { x: 0.5, y: 0.5, width: 0.2, height: 0.4 };
      const container = { width: 200, height: 400 };

      const result = anchorPoint(bbox, container);

      // x = (0.5 + 0.2/2) * 200 = 120
      // y = (0.5 + 0.4*0.25) * 400 = 240
      expect(result.x).toBe(120);
      expect(result.y).toBe(240);
    });

    it('should handle edge case at origin', () => {
      const bbox = { x: 0, y: 0, width: 0.1, height: 0.2 };
      const container = { width: 100, height: 100 };

      const result = anchorPoint(bbox, container);

      // x = (0 + 0.1/2) * 100 = 5
      // y = (0 + 0.2*0.25) * 100 = 5
      expect(result.x).toBe(5);
      expect(result.y).toBe(5);
    });
  });

  describe('opacity', () => {
    it('should return 0.85 for confidence >= 0.85', () => {
      expect(opacity(0.92)).toBe(0.85);
      expect(opacity(0.85)).toBe(0.85);
      expect(opacity(1.0)).toBe(0.85);
    });

    it('should return 0.75 for confidence 0.65-0.85', () => {
      expect(opacity(0.75)).toBe(0.75);
      expect(opacity(0.65)).toBe(0.75);
      expect(opacity(0.84)).toBe(0.75);
    });

    it('should return 0.65 for confidence 0.45-0.65', () => {
      expect(opacity(0.55)).toBe(0.65);
      expect(opacity(0.45)).toBe(0.65);
      expect(opacity(0.64)).toBe(0.65);
    });

    it('should return 0.0 for confidence < 0.45', () => {
      expect(opacity(0.40)).toBe(0.0);
      expect(opacity(0.0)).toBe(0.0);
      expect(opacity(0.44)).toBe(0.0);
    });
  });

  describe('isVisible', () => {
    it('should return true for confidence >= 0.45', () => {
      expect(isVisible(0.45)).toBe(true);
      expect(isVisible(0.90)).toBe(true);
      expect(isVisible(0.5)).toBe(true);
    });

    it('should return false for confidence < 0.45', () => {
      expect(isVisible(0.44)).toBe(false);
      expect(isVisible(0.0)).toBe(false);
      expect(isVisible(0.3)).toBe(false);
    });
  });

  describe('isTappable', () => {
    it('should return true for confidence >= 0.65', () => {
      expect(isTappable(0.65)).toBe(true);
      expect(isTappable(0.90)).toBe(true);
      expect(isTappable(0.7)).toBe(true);
    });

    it('should return false for confidence < 0.65', () => {
      expect(isTappable(0.64)).toBe(false);
      expect(isTappable(0.0)).toBe(false);
      expect(isTappable(0.5)).toBe(false);
    });
  });

  describe('confidenceLabel', () => {
    it('should return "Widely rated" for confidence >= 0.85', () => {
      expect(confidenceLabel(0.85)).toBe('Widely rated');
      expect(confidenceLabel(0.95)).toBe('Widely rated');
      expect(confidenceLabel(1.0)).toBe('Widely rated');
    });

    it('should return null for confidence < 0.85', () => {
      expect(confidenceLabel(0.84)).toBeNull();
      expect(confidenceLabel(0.5)).toBeNull();
      expect(confidenceLabel(0.0)).toBeNull();
    });
  });

  describe('badgeSize', () => {
    it('should return larger size for top three', () => {
      const result = badgeSize(true);
      expect(result).toEqual({ width: 52, height: 28 });
    });

    it('should return base size for non-top three', () => {
      const result = badgeSize(false);
      expect(result).toEqual({ width: 44, height: 24 });
    });
  });

  describe('adjustedAnchorPoint', () => {
    const defaultBadgeSize = { width: 44, height: 24 };
    const container = { width: 100, height: 100 };

    it('should clamp point at left edge inward', () => {
      const point = { x: 10, y: 50 };
      const bbox = { x: 0, y: 0.4, width: 0.1, height: 0.3 };

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // Should be clamped to badgeWidth/2 + padding = 22 + 4 = 26
      expect(result.x).toBe(26);
      expect(result.y).toBe(50);
    });

    it('should clamp point at right edge inward', () => {
      const point = { x: 95, y: 50 };
      const bbox = { x: 0.9, y: 0.4, width: 0.1, height: 0.3 };

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // Should be clamped to containerWidth - badgeWidth/2 - padding = 100 - 22 - 4 = 74
      expect(result.x).toBe(74);
      expect(result.y).toBe(50);
    });

    it('should clamp point at top edge inward', () => {
      const point = { x: 50, y: 5 };
      const bbox = { x: 0.4, y: 0, width: 0.2, height: 0.3 };

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // Should be clamped to badgeHeight/2 + padding = 12 + 4 = 16
      expect(result.x).toBe(50);
      expect(result.y).toBe(16);
    });

    it('should clamp point at bottom edge inward', () => {
      const point = { x: 50, y: 95 };
      const bbox = { x: 0.4, y: 0.7, width: 0.2, height: 0.3 };

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // Should be clamped to containerHeight - badgeHeight/2 - padding = 100 - 12 - 4 = 84
      expect(result.x).toBe(50);
      expect(result.y).toBe(84);
    });

    it('should not modify point that is already within bounds', () => {
      const point = { x: 50, y: 50 };
      const bbox = { x: 0.4, y: 0.4, width: 0.2, height: 0.3 };

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      expect(result.x).toBe(50);
      expect(result.y).toBe(50);
    });

    it('should anchor higher for partial bottles (bbox.height < 0.15)', () => {
      const point = { x: 50, y: 50 };
      const bbox = { x: 0.4, y: 0.3, width: 0.2, height: 0.1 }; // height < 0.15

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // Should anchor at bbox.y * containerHeight + badgeHeight/2 + 4 = 0.3 * 100 + 12 + 4 = 46
      expect(result.x).toBe(50);
      expect(result.y).toBe(46);
    });

    it('should use normal anchor for non-partial bottles', () => {
      const point = { x: 50, y: 47.5 };
      const bbox = { x: 0.4, y: 0.4, width: 0.2, height: 0.3 }; // height >= 0.15

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // y should remain at original value (no partial bottle adjustment)
      expect(result.x).toBe(50);
      expect(result.y).toBe(47.5);
    });

    it('should handle combined clamping and partial bottle adjustment', () => {
      const point = { x: 5, y: 5 };
      const bbox = { x: 0, y: 0.02, width: 0.1, height: 0.1 }; // partial bottle at top-left

      const result = adjustedAnchorPoint(point, bbox, container, defaultBadgeSize);

      // x clamped to 26 (badgeWidth/2 + padding)
      // y for partial bottle = 0.02 * 100 + 12 + 4 = 18, but clamped to min 16
      expect(result.x).toBe(26);
      expect(result.y).toBe(18);
    });
  });

  describe('cornerBrackets', () => {
    it('should return 8 line segments', () => {
      const bbox = { x: 0.2, y: 0.2, width: 0.3, height: 0.5 };
      const container = { width: 400, height: 600 };

      const lines = cornerBrackets(bbox, container);

      expect(lines).toHaveLength(8);
    });

    it('should clamp arm length to min (8px) for tiny bboxes', () => {
      // Very small bbox: width=0.01, height=0.01
      // armH = 0.01 * 400 * 0.18 = 0.72 → clamped to 8
      // armV = 0.01 * 600 * 0.18 = 1.08 → clamped to 8
      const bbox = { x: 0.5, y: 0.5, width: 0.01, height: 0.01 };
      const container = { width: 400, height: 600 };

      const lines = cornerBrackets(bbox, container);

      // Top-left horizontal arm: x2 - x1 should be 8 (min arm)
      const topLeftH = lines[0];
      expect(Math.abs(topLeftH.x2 - topLeftH.x1)).toBe(8);

      // Top-left vertical arm: y2 - y1 should be 8 (min arm)
      const topLeftV = lines[1];
      expect(Math.abs(topLeftV.y2 - topLeftV.y1)).toBe(8);
    });

    it('should clamp arm length to max (40px) for huge bboxes', () => {
      // Large bbox: width=0.9, height=0.9
      // armH = 0.9 * 1000 * 0.18 = 162 → clamped to 40
      // armV = 0.9 * 1000 * 0.18 = 162 → clamped to 40
      const bbox = { x: 0.05, y: 0.05, width: 0.9, height: 0.9 };
      const container = { width: 1000, height: 1000 };

      const lines = cornerBrackets(bbox, container);

      // Top-left horizontal arm: x2 - x1 should be 40 (max arm)
      const topLeftH = lines[0];
      expect(Math.abs(topLeftH.x2 - topLeftH.x1)).toBe(40);

      // Top-left vertical arm: y2 - y1 should be 40 (max arm)
      const topLeftV = lines[1];
      expect(Math.abs(topLeftV.y2 - topLeftV.y1)).toBe(40);
    });

    it('should match pixel conversion of bbox corners', () => {
      const bbox = { x: 0.25, y: 0.40, width: 0.10, height: 0.30 };
      const container = { width: 400, height: 600 };

      const lines = cornerBrackets(bbox, container);

      const expectedLeft = 0.25 * 400;   // 100
      const expectedTop = 0.40 * 600;    // 240
      const expectedRight = (0.25 + 0.10) * 400;  // 140
      const expectedBottom = (0.40 + 0.30) * 600;  // 420

      // Top-left corner: both lines start at (left, top)
      expect(lines[0].x1).toBe(expectedLeft);
      expect(lines[0].y1).toBe(expectedTop);
      expect(lines[1].x1).toBe(expectedLeft);
      expect(lines[1].y1).toBe(expectedTop);

      // Top-right corner: both lines start at (right, top)
      expect(lines[2].x1).toBe(expectedRight);
      expect(lines[2].y1).toBe(expectedTop);
      expect(lines[3].x1).toBe(expectedRight);
      expect(lines[3].y1).toBe(expectedTop);

      // Bottom-left corner: both lines start at (left, bottom)
      expect(lines[4].x1).toBe(expectedLeft);
      expect(lines[4].y1).toBe(expectedBottom);
      expect(lines[5].x1).toBe(expectedLeft);
      expect(lines[5].y1).toBe(expectedBottom);

      // Bottom-right corner: both lines start at (right, bottom)
      expect(lines[6].x1).toBe(expectedRight);
      expect(lines[6].y1).toBe(expectedBottom);
      expect(lines[7].x1).toBe(expectedRight);
      expect(lines[7].y1).toBe(expectedBottom);
    });
  });
});
