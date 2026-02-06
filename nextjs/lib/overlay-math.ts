/**
 * Centralized overlay placement math
 * All calculations for positioning rating badges on wine bottles
 *
 * Centralized overlay placement math for the web app
 */

import { BoundingBox, Point, Size } from './types';
import { badgeSizes, bracketConfig, layout } from './theme';

// MARK: - Confidence Thresholds

/** Minimum confidence to show overlay (opacity 0.8) */
export const VISIBILITY_THRESHOLD = 0.45;

/** Minimum confidence for tappable overlays (opacity 0.9) */
export const TAPPABLE_THRESHOLD = 0.65;

/** Minimum confidence for "Widely rated" label (opacity 1.0) */
export const HIGH_CONFIDENCE_THRESHOLD = 0.85;

// MARK: - Badge Sizing (re-export from theme for backwards compatibility)

/** Base badge size */
export const BASE_BADGE_SIZE: Size = badgeSizes.base;

/** Top-3 badge size (larger) */
export const TOP_THREE_BADGE_SIZE: Size = badgeSizes.topThree;

// MARK: - Anchor Point Calculation

/**
 * Calculate the anchor point for a rating badge
 * @param bbox - Normalized bounding box (0-1)
 * @param containerSize - Container size in pixels
 * @returns Screen position for badge center
 */
export function anchorPoint(bbox: BoundingBox, containerSize: Size): Point {
  // Anchor at horizontal center, vertical 25% from top
  const x = (bbox.x + bbox.width / 2) * containerSize.width;
  const y = (bbox.y + bbox.height * 0.25) * containerSize.height;
  return { x, y };
}

// MARK: - Opacity

/**
 * Confidence-based opacity for badges
 * | Confidence | Opacity |
 * |------------|---------|
 * | >= 0.85    | 1.0     |
 * | 0.65-0.85  | 0.9     |
 * | 0.45-0.65  | 0.8     |
 * | < 0.45     | 0.0     |
 */
export function opacity(confidence: number): number {
  if (confidence >= 0.85) {
    return 1.0;
  } else if (confidence >= 0.65) {
    return 0.9;
  } else if (confidence >= 0.45) {
    return 0.8;
  } else {
    return 0.0;
  }
}

// MARK: - Visibility

/**
 * Whether a wine should be visible (confidence >= 0.45)
 */
export function isVisible(confidence: number): boolean {
  return confidence >= VISIBILITY_THRESHOLD;
}

/**
 * Whether a wine should be tappable (confidence >= 0.65)
 */
export function isTappable(confidence: number): boolean {
  return confidence >= TAPPABLE_THRESHOLD;
}

/**
 * Confidence label for detail sheet ("Widely rated" for high confidence, null otherwise)
 */
export function confidenceLabel(confidence: number): string | null {
  return confidence >= HIGH_CONFIDENCE_THRESHOLD ? 'Widely rated' : null;
}

// MARK: - Badge Sizing

/**
 * Get badge size based on whether it's in top 3
 */
export function badgeSize(isTopThree: boolean): Size {
  return isTopThree ? TOP_THREE_BADGE_SIZE : BASE_BADGE_SIZE;
}

// MARK: - Collision Avoidance

/**
 * Adjust anchor point to avoid collisions
 * @param point - Original anchor point
 * @param bbox - Bounding box for the bottle (normalized 0-1)
 * @param containerSize - Container size in pixels
 * @param badgeSizeValue - Size of the rating badge
 * @returns Adjusted point clamped to image bounds
 */
export function adjustedAnchorPoint(
  point: Point,
  bbox: BoundingBox,
  containerSize: Size,
  badgeSizeValue: Size
): Point {
  let adjustedX = point.x;
  let adjustedY = point.y;

  const padding = layout.collisionPadding;

  // If bbox height is small (partial bottle), anchor higher
  if (bbox.height < 0.15) {
    adjustedY = bbox.y * containerSize.height + badgeSizeValue.height / 2 + padding;
  }

  // Clamp to image bounds with padding
  adjustedX = Math.max(
    badgeSizeValue.width / 2 + padding,
    Math.min(adjustedX, containerSize.width - badgeSizeValue.width / 2 - padding)
  );
  adjustedY = Math.max(
    badgeSizeValue.height / 2 + padding,
    Math.min(adjustedY, containerSize.height - badgeSizeValue.height / 2 - padding)
  );

  return { x: adjustedX, y: adjustedY };
}

// MARK: - Corner Brackets

/** A single line segment for a corner bracket */
export interface CornerBracketLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * Compute 8 line segments (2 per corner) forming "L"-shaped corner brackets
 * around a bounding box.
 *
 * @param bbox - Normalized bounding box (0-1)
 * @param containerSize - Container size in pixels
 * @returns Array of 8 line segments in pixel coordinates
 */
export function cornerBrackets(bbox: BoundingBox, containerSize: Size): CornerBracketLine[] {
  const left = bbox.x * containerSize.width;
  const top = bbox.y * containerSize.height;
  const right = (bbox.x + bbox.width) * containerSize.width;
  const bottom = (bbox.y + bbox.height) * containerSize.height;

  const clamp = (v: number, min: number, max: number) => Math.min(Math.max(v, min), max);

  const armH = clamp(bbox.width * containerSize.width * bracketConfig.armFraction, bracketConfig.minArm, bracketConfig.maxArm);
  const armV = clamp(bbox.height * containerSize.height * bracketConfig.armFraction, bracketConfig.minArm, bracketConfig.maxArm);

  return [
    // Top-left: horizontal right, vertical down
    { x1: left, y1: top, x2: left + armH, y2: top },
    { x1: left, y1: top, x2: left, y2: top + armV },
    // Top-right: horizontal left, vertical down
    { x1: right, y1: top, x2: right - armH, y2: top },
    { x1: right, y1: top, x2: right, y2: top + armV },
    // Bottom-left: horizontal right, vertical up
    { x1: left, y1: bottom, x2: left + armH, y2: bottom },
    { x1: left, y1: bottom, x2: left, y2: bottom - armV },
    // Bottom-right: horizontal left, vertical up
    { x1: right, y1: bottom, x2: right - armH, y2: bottom },
    { x1: right, y1: bottom, x2: right, y2: bottom - armV },
  ];
}
