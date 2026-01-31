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
}

const STAR_COLOR = '#FFCC00';
const TOP_THREE_BORDER_COLOR = 'rgba(255, 204, 0, 0.6)';

export function RatingBadge({
  rating,
  confidence,
  isTopThree,
  onPress,
}: RatingBadgeProps) {
  const size = badgeSize(isTopThree);
  const badgeOpacity = opacity(confidence);
  const canTap = isTappable(confidence) && onPress !== undefined;

  const containerStyle: ViewStyle = {
    width: size.width,
    height: size.height,
    opacity: badgeOpacity,
    borderWidth: isTopThree ? 2 : 0,
    borderColor: isTopThree ? TOP_THREE_BORDER_COLOR : 'transparent',
  };

  const content = (
    <View style={[styles.badge, containerStyle]}>
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
      <TouchableOpacity onPress={onPress} activeOpacity={0.8}>
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
