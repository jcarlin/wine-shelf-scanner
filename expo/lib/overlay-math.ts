/**
 * Centralized overlay placement math
 * All calculations for positioning rating badges on wine bottles
 *
 * Direct port of ios/WineShelfScanner/Utils/OverlayMath.swift
 */

import { BoundingBox, Point, Size } from './types';

// MARK: - Confidence Thresholds

/** Minimum confidence to show overlay (opacity 0.5) */
export const VISIBILITY_THRESHOLD = 0.45;

/** Minimum confidence for tappable overlays (opacity 0.75) */
export const TAPPABLE_THRESHOLD = 0.65;

/** Minimum confidence for "Widely rated" label (opacity 1.0) */
export const HIGH_CONFIDENCE_THRESHOLD = 0.85;

// MARK: - Badge Sizing

/** Base badge size */
export const BASE_BADGE_SIZE: Size = { width: 44, height: 24 };

/** Top-3 badge size (larger) */
export const TOP_THREE_BADGE_SIZE: Size = { width: 52, height: 28 };

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
 * | 0.65-0.85  | 0.75    |
 * | 0.45-0.65  | 0.5     |
 * | < 0.45     | 0.0     |
 */
export function opacity(confidence: number): number {
  if (confidence >= 0.85) {
    return 1.0;
  } else if (confidence >= 0.65) {
    return 0.75;
  } else if (confidence >= 0.45) {
    return 0.5;
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
 * Confidence label for detail sheet ("Widely rated" or "Limited data")
 */
export function confidenceLabel(confidence: number): string {
  return confidence >= HIGH_CONFIDENCE_THRESHOLD ? 'Widely rated' : 'Limited data';
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

  // If bbox height is small (partial bottle), anchor higher
  if (bbox.height < 0.15) {
    adjustedY = bbox.y * containerSize.height + badgeSizeValue.height / 2 + 4;
  }

  // Clamp to image bounds with padding
  const padding = 4;
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
