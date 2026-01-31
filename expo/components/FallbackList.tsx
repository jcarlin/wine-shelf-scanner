import React from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
} from 'react-native';
import { FallbackWine } from '../lib/types';
import { colors, spacing, fontSize } from '../lib/theme';

interface FallbackListProps {
  wines: FallbackWine[];
}

export function FallbackList({ wines }: FallbackListProps) {
  // Sort by rating descending
  const sortedWines = [...wines].sort((a, b) => b.rating - a.rating);

  const renderItem = ({ item, index }: { item: FallbackWine; index: number }) => (
    <View style={styles.item} testID={`fallbackItem_${index}`}>
      <Text style={styles.wineName} numberOfLines={2} testID={`fallbackWineName_${index}`}>
        {item.wine_name}
      </Text>
      <View style={styles.ratingContainer}>
        <Text style={styles.star}>{'\u2605'}</Text>
        <Text style={styles.ratingText} testID={`fallbackRating_${index}`}>{item.rating.toFixed(1)}</Text>
      </View>
    </View>
  );

  return (
    <FlatList
      data={sortedWines}
      renderItem={renderItem}
      keyExtractor={(item, index) => `${item.wine_name}-${index}`}
      contentContainerStyle={styles.listContent}
      ItemSeparatorComponent={() => <View style={styles.separator} />}
      testID="fallbackList"
    />
  );
}

const styles = StyleSheet.create({
  listContent: {
    padding: spacing.md,
  },
  item: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm + spacing.xs,
  },
  wineName: {
    flex: 1,
    fontSize: fontSize.md,
    color: colors.textDark,
    marginRight: spacing.md,
  },
  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  star: {
    fontSize: fontSize.md,
    color: colors.star,
  },
  ratingText: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.textDark,
  },
  separator: {
    height: 1,
    backgroundColor: colors.separator,
  },
});
