import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ViewStyle,
} from 'react-native';
import { isTappable, badgeSize, opacity } from '../lib/overlay-math';
import { colors, spacing, borderRadius, fontSize } from '../lib/theme';

interface RatingBadgeProps {
  rating: number;
  confidence: number;
  isTopThree: boolean;
  onPress?: () => void;
  /** Wine name for accessibility testID */
  wineName?: string;
}

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
        shadowColor: colors.topThreeGlow,
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
    borderColor: isTopThree ? colors.topThreeBorder : 'transparent',
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
    backgroundColor: colors.badgeBackground,
    borderRadius: borderRadius.md,
    paddingHorizontal: 6,
    gap: 2,
    shadowColor: colors.textDark,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.5,
    shadowRadius: 2,
    elevation: 4,
  },
  star: {
    fontSize: 12,
    color: colors.star,
  },
  starTopThree: {
    fontSize: 14,
  },
  rating: {
    fontSize: 13,
    fontWeight: 'bold',
    color: colors.textLight,
  },
  ratingTopThree: {
    fontSize: fontSize.sm,
  },
});
