'use client';

import { useMemo } from 'react';
import { WineResult, Size, Rect } from '@/lib/types';
import { useFeatureFlags } from '@/lib/feature-flags';
import { useWineMemory } from '@/hooks/useWineMemory';
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
  const { shelfRanking, safePick, wineMemory } = useFeatureFlags();
  const memory = useWineMemory();

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

  // Compute shelf rankings
  const shelfRankings = useMemo(() => {
    if (!shelfRanking) return new Map<string, { rank: number; total: number }>();
    const ranked = [...visibleWines]
      .filter((w) => w.rating !== null)
      .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
    if (ranked.length < 3) return new Map<string, { rank: number; total: number }>();
    const rankings = new Map<string, { rank: number; total: number }>();
    let currentRank = 1;
    ranked.forEach((wine, index) => {
      if (index > 0 && wine.rating !== ranked[index - 1].rating) {
        currentRank = index + 1;
      }
      rankings.set(wine.wine_name, { rank: currentRank, total: ranked.length });
    });
    return rankings;
  }, [shelfRanking, visibleWines]);

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
