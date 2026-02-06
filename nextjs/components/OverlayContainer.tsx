'use client';

import { useMemo } from 'react';
import { WineResult, Size, Rect } from '@/lib/types';
import { useFeatureFlags } from '@/lib/feature-flags';
import { useWineMemory } from '@/hooks/useWineMemory';
import { RatingBadge } from './RatingBadge';
import { CornerBrackets } from './CornerBrackets';
import { isVisible, anchorPoint, adjustedAnchorPoint, badgeSize } from '@/lib/overlay-math';
import { computeShelfRankings, getTopWineNames } from '@/lib/shelf-rankings';

interface OverlayContainerProps {
  wines: WineResult[];
  imageBounds: Rect;
  onWineSelect: (wine: WineResult) => void;
}

export function OverlayContainer({ wines, imageBounds, onWineSelect }: OverlayContainerProps) {
  const { shelfRanking, safePick, wineMemory, cornerBrackets } = useFeatureFlags();
  const memory = useWineMemory();

  // Filter to visible wines only
  const visibleWines = useMemo(() => {
    return wines.filter((wine) => isVisible(wine.confidence));
  }, [wines]);

  // Determine top 3 by rating
  const topThreeIds = useMemo(() => getTopWineNames(wines), [wines]);

  // Compute shelf rankings
  const shelfRankings = useMemo(() => {
    if (!shelfRanking) return new Map<string, { rank: number; total: number }>();
    return computeShelfRankings(wines);
  }, [shelfRanking, wines]);

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

  const containerSize: Size = {
    width: imageBounds.width,
    height: imageBounds.height,
  };
  const offset = { x: imageBounds.x, y: imageBounds.y };

  return (
    <>
      {cornerBrackets &&
        winePositions
          .filter(({ isTopThree }) => isTopThree)
          .map(({ wine }) => (
            <CornerBrackets
              key={`bracket-${wine.wine_name}-${wine.bbox.x.toFixed(3)}`}
              bbox={wine.bbox}
              containerSize={containerSize}
              offset={offset}
              isBestPick={topThreeIds[0] === wine.wine_name}
            />
          ))}
      {winePositions.map(({ wine, isTopThree, position }, index) => (
        <RatingBadge
          key={`${wine.wine_name}-${wine.bbox.x.toFixed(3)}-${wine.bbox.y.toFixed(3)}`}
          wine={wine}
          isTopThree={isTopThree}
          position={position}
          onClick={() => onWineSelect(wine)}
          shelfRank={shelfRankings.get(wine.wine_name)?.rank}
          isSafePick={safePick && wine.is_safe_pick === true}
          userSentiment={wineMemory ? memory.get(wine.wine_name) : undefined}
        />
      ))}
    </>
  );
}
