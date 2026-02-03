'use client';

import { useMemo } from 'react';
import { WineResult, Size, Rect } from '@/lib/types';
import { RatingBadge } from './RatingBadge';
import {
  isVisible,
  anchorPoint,
  adjustedAnchorPoint,
  badgeSize
} from '@/lib/overlay-math';

interface OverlayContainerProps {
  wines: WineResult[];
  imageBounds: Rect;
  onWineSelect: (wine: WineResult) => void;
}

export function OverlayContainer({ wines, imageBounds, onWineSelect }: OverlayContainerProps) {
  // Filter to visible wines only
  const visibleWines = useMemo(() => {
    return wines.filter((wine) => isVisible(wine.confidence));
  }, [wines]);

  // Determine top 3 by rating
  const topThreeIds = useMemo(() => {
    return [...visibleWines]
      .filter((w) => w.rating !== null)
      .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
      .slice(0, 3)
      .map((w) => w.wine_name);
  }, [visibleWines]);

  // Calculate positions for each wine
  const winePositions = useMemo(() => {
    const containerSize: Size = {
      width: imageBounds.width,
      height: imageBounds.height,
    };

    return visibleWines.map((wine) => {
      const isTopThree = topThreeIds.includes(wine.wine_name);
      const size = badgeSize(isTopThree);

      // Calculate anchor point relative to image bounds
      const anchor = anchorPoint(wine.bbox, containerSize);
      const adjusted = adjustedAnchorPoint(anchor, wine.bbox, containerSize, size);

      // Offset by image bounds position (for letterboxing)
      return {
        wine,
        isTopThree,
        position: {
          x: imageBounds.x + adjusted.x,
          y: imageBounds.y + adjusted.y,
        },
      };
    });
  }, [visibleWines, topThreeIds, imageBounds]);

  return (
    <>
      {winePositions.map(({ wine, isTopThree, position }) => (
        <RatingBadge
          key={wine.wine_name}
          wine={wine}
          isTopThree={isTopThree}
          position={position}
          onClick={() => onWineSelect(wine)}
        />
      ))}
    </>
  );
}
