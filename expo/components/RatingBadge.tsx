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

export type WineSentiment = 'liked' | 'disliked';

interface RatingBadgeProps {
  rating: number;
  confidence: number;
  isTopThree: boolean;
  onPress?: () => void;
  wineName?: string;
  shelfRank?: number;
  isSafePick?: boolean;
  userSentiment?: WineSentiment;
}

export function RatingBadge({
  rating,
  confidence,
  isTopThree,
  onPress,
  wineName,
  shelfRank,
  isSafePick,
  userSentiment,
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

  const rankColor = shelfRank === 1 ? colors.star : shelfRank === 2 ? '#D9D9D9' : '#B3B3B3';

  const content = (
    <View style={styles.badgeColumn} testID={testID}>
      <View>
        <View style={[styles.badge, containerStyle]}>
          <Text style={[styles.star, isTopThree && styles.starTopThree]}>
            {'\u2605'}
          </Text>
          <Text style={[styles.rating, isTopThree && styles.ratingTopThree]}>
            {rating.toFixed(1)}
          </Text>
          {isSafePick && (
            <Text style={styles.shieldIcon}>{'\u2713'}</Text>
          )}
        </View>
        {userSentiment && (
          <View style={styles.sentimentIndicator}>
            <Text style={userSentiment === 'disliked' ? styles.sentimentDisliked : styles.sentimentLiked}>
              {userSentiment === 'disliked' ? '\u2715' : '\u2665'}
            </Text>
          </View>
        )}
      </View>
      {shelfRank !== undefined && (
        <Text style={[styles.rankText, { color: rankColor }]}>
          #{shelfRank}
        </Text>
      )}
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
  badgeColumn: {
    alignItems: 'center',
    gap: 2,
  },
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
  shieldIcon: {
    fontSize: 9,
    color: '#4CAF50',
    fontWeight: 'bold',
  },
  rankText: {
    fontSize: 9,
    fontWeight: 'bold',
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 1,
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
  sentimentIndicator: {
    position: 'absolute',
    top: -6,
    right: -6,
  },
  sentimentDisliked: {
    fontSize: 12,
    color: '#FF3B30',
    fontWeight: 'bold',
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 1,
  },
  sentimentLiked: {
    fontSize: 12,
    color: '#34C759',
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 1,
  },
});
