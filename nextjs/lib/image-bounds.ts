/**
 * Image bounds calculation for overlay positioning
 *
 * CRITICAL: When using object-fit: contain, the image may have letterboxing.
 * Overlays must be positioned relative to the actual image bounds, not the container.
 */

import { Rect, Size } from './types';

/**
 * Calculate the actual image bounds within a container when using "contain" resize mode
 *
 * With object-fit: contain, the image scales to fit while maintaining aspect ratio,
 * potentially leaving letterbox areas (black bars) on sides or top/bottom.
 *
 * @param imageSize - Original image dimensions
 * @param containerSize - Container dimensions
 * @returns Rectangle describing where the image actually renders within the container
 */
export function getImageBounds(imageSize: Size, containerSize: Size): Rect {
  const imageAspect = imageSize.width / imageSize.height;
  const containerAspect = containerSize.width / containerSize.height;

  if (imageAspect > containerAspect) {
    // Image is wider than container - letterbox top/bottom
    const scaledHeight = containerSize.width / imageAspect;
    const y = (containerSize.height - scaledHeight) / 2;
    return {
      x: 0,
      y,
      width: containerSize.width,
      height: scaledHeight,
    };
  } else {
    // Image is taller than container - letterbox left/right
    const scaledWidth = containerSize.height * imageAspect;
    const x = (containerSize.width - scaledWidth) / 2;
    return {
      x,
      y: 0,
      width: scaledWidth,
      height: containerSize.height,
    };
  }
}

/**
 * Convert normalized coordinates (0-1) to screen coordinates
 * accounting for image letterboxing
 *
 * @param normalizedX - X coordinate in 0-1 range
 * @param normalizedY - Y coordinate in 0-1 range
 * @param imageBounds - Actual image bounds from getImageBounds()
 * @returns Screen coordinates
 */
export function normalizedToScreen(
  normalizedX: number,
  normalizedY: number,
  imageBounds: Rect
): { x: number; y: number } {
  return {
    x: imageBounds.x + normalizedX * imageBounds.width,
    y: imageBounds.y + normalizedY * imageBounds.height,
  };
}
