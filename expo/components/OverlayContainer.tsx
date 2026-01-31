import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import { WineResult, Size } from '../lib/types';
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

export function OverlayContainer({
  results,
  imageSize,
  containerSize,
}: OverlayContainerProps) {
  const [selectedWine, setSelectedWine] = useState<WineResult | null>(null);

  // Filter to visible wines only (confidence >= 0.45)
  const visibleWines = results.filter((wine) => isVisible(wine.confidence));

  // Determine top 3 by sorting by rating (descending) and taking first 3
  const sortedByRating = [...visibleWines]
    .filter((wine) => wine.rating !== null)
    .sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  const topThreeIds = new Set(sortedByRating.slice(0, 3).map((w) => w.wine_name));

  // Calculate actual image bounds accounting for letterboxing
  const imageBounds = getImageBounds(imageSize, containerSize);

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
                onPress={() => setSelectedWine(wine)}
                wineName={wine.wine_name}
              />
            </View>
          );
        })}
      </View>

      <WineDetailModal
        visible={selectedWine !== null}
        wine={selectedWine}
        onClose={() => setSelectedWine(null)}
      />
    </>
  );
}

const styles = StyleSheet.create({
  badgeWrapper: {
    position: 'absolute',
  },
});
