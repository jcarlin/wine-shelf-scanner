import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ViewStyle,
} from 'react-native';
import { isTappable, badgeSize, opacity } from '../lib/overlay-math';

interface RatingBadgeProps {
  rating: number;
  confidence: number;
  isTopThree: boolean;
  onPress?: () => void;
  /** Wine name for accessibility testID */
  wineName?: string;
}

const STAR_COLOR = '#FFCC00';
const TOP_THREE_BORDER_COLOR = 'rgba(255, 204, 0, 0.6)';
const TOP_THREE_GLOW_COLOR = '#FFCC00';

export function RatingBadge({
  rating,
  confidence,
  isTopThree,
  onPress,
  wineName,
}: RatingBadgeProps) {
  // Generate testID from wine name (sanitize for valid ID)
  const testID = wineName
    ? `ratingBadge_${wineName.replace(/[^a-zA-Z0-9]/g, '_')}`
    : 'ratingBadge';
  const size = badgeSize(isTopThree);
  const badgeOpacity = opacity(confidence);
  const canTap = isTappable(confidence) && onPress !== undefined;

  // Glow effect for top-3 wines
  const glowStyle: ViewStyle = isTopThree
    ? {
        shadowColor: TOP_THREE_GLOW_COLOR,
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.6,
        shadowRadius: 4,
        elevation: 8, // Android
      }
    : {};

  const containerStyle: ViewStyle = {
    width: size.width,
    height: size.height,
    opacity: badgeOpacity,
    borderWidth: isTopThree ? 2 : 0,
    borderColor: isTopThree ? TOP_THREE_BORDER_COLOR : 'transparent',
    ...glowStyle,
  };

  const content = (
    <View style={[styles.badge, containerStyle]} testID={testID}>
      <Text style={[styles.star, isTopThree && styles.starTopThree]}>
        {'\u2605'}
      </Text>
      <Text style={[styles.rating, isTopThree && styles.ratingTopThree]}>
        {rating.toFixed(1)}
      </Text>
    </View>
  );

  if (canTap) {
    return (
      <TouchableOpacity onPress={onPress} activeOpacity={0.8} testID={`${testID}_touchable`}>
        {content}
      </TouchableOpacity>
    );
  }

  return content;
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    borderRadius: 12,
    paddingHorizontal: 6,
    gap: 2,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.5,
    shadowRadius: 2,
    elevation: 4,
  },
  star: {
    fontSize: 12,
    color: STAR_COLOR,
  },
  starTopThree: {
    fontSize: 14,
  },
  rating: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  ratingTopThree: {
    fontSize: 15,
  },
});
