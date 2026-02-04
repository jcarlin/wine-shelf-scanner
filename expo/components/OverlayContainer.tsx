import React, { useState, useMemo, useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
import { WineResult, Size } from '../lib/types';
import { useFeatureFlags } from '../lib/feature-flags';
import { useWineMemory } from '../hooks/useWineMemory';
import { getImageBounds } from '../lib/image-bounds';
import {
  anchorPoint,
  adjustedAnchorPoint,
  badgeSize,
  isVisible,
} from '../lib/overlay-math';
import { RatingBadge } from './RatingBadge';
import { WineDetailModal } from './WineDetailModal';

interface OverlayContainerProps {
  results: WineResult[];
  imageSize: Size;
  containerSize: Size;
}

export const OverlayContainer = React.memo(function OverlayContainer({
  results,
  imageSize,
  containerSize,
}: OverlayContainerProps) {
  const [selectedWine, setSelectedWine] = useState<WineResult | null>(null);
  const { shelfRanking, safePick, wineMemory } = useFeatureFlags();
  const memory = useWineMemory();

  // Memoize visible wines filtering
  const visibleWines = useMemo(
    () => results.filter((wine) => isVisible(wine.confidence)),
    [results]
  );

  // Memoize top 3 calculation to avoid recalculating on every render
  const topThreeIds = useMemo(() => {
    const sorted = [...visibleWines]
      .filter((wine) => wine.rating !== null)
      .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
    return new Set(sorted.slice(0, 3).map((w) => w.wine_name));
  }, [visibleWines]);

  // Compute shelf rankings (rank by rating, ties share rank)
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

  // Memoize image bounds calculation
  const imageBounds = useMemo(
    () => getImageBounds(imageSize, containerSize),
    [imageSize, containerSize]
  );

  // Memoize handlers
  const handleWineSelect = useCallback((wine: WineResult) => {
    setSelectedWine(wine);
  }, []);

  const handleModalClose = useCallback(() => {
    setSelectedWine(null);
  }, []);

  return (
    <>
      <View style={StyleSheet.absoluteFill} pointerEvents="box-none" testID="overlayContainer">
        {visibleWines.map((wine, index) => {
          const isTopThree = topThreeIds.has(wine.wine_name);
          const size = badgeSize(isTopThree);

          // Calculate anchor point within the actual image bounds
          const anchor = anchorPoint(wine.bbox, {
            width: imageBounds.width,
            height: imageBounds.height,
          });

          // Adjust for collision avoidance and clamping
          const adjusted = adjustedAnchorPoint(
            anchor,
            wine.bbox,
            { width: imageBounds.width, height: imageBounds.height },
            size
          );

          // Offset by image bounds position (for letterboxing)
          const screenX = imageBounds.x + adjusted.x;
          const screenY = imageBounds.y + adjusted.y;

          return (
            <View
              key={`${wine.wine_name}-${index}`}
              style={[
                styles.badgeWrapper,
                {
                  left: screenX,
                  top: screenY,
                  transform: [
                    { translateX: -size.width / 2 },
                    { translateY: -size.height / 2 },
                  ],
                },
              ]}
            >
              <RatingBadge
                rating={wine.rating ?? 0}
                confidence={wine.confidence}
                isTopThree={isTopThree}
                onPress={() => handleWineSelect(wine)}
                wineName={wine.wine_name}
                shelfRank={shelfRankings.get(wine.wine_name)?.rank}
                isSafePick={safePick && wine.is_safe_pick === true}
                userSentiment={wineMemory ? memory.get(wine.wine_name) : undefined}
              />
            </View>
          );
        })}
      </View>

      <WineDetailModal
        visible={selectedWine !== null}
        wine={selectedWine}
        onClose={handleModalClose}
        shelfRank={selectedWine ? shelfRankings.get(selectedWine.wine_name)?.rank : undefined}
        shelfTotal={selectedWine ? shelfRankings.get(selectedWine.wine_name)?.total : undefined}
      />
    </>
  );
});

const styles = StyleSheet.create({
  badgeWrapper: {
    position: 'absolute',
  },
});
