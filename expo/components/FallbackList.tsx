import React from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
} from 'react-native';
import { FallbackWine } from '../lib/types';

interface FallbackListProps {
  wines: FallbackWine[];
}

const STAR_COLOR = '#FFCC00';

export function FallbackList({ wines }: FallbackListProps) {
  // Sort by rating descending
  const sortedWines = [...wines].sort((a, b) => b.rating - a.rating);

  const renderItem = ({ item }: { item: FallbackWine }) => (
    <View style={styles.item}>
      <Text style={styles.wineName} numberOfLines={2}>
        {item.wine_name}
      </Text>
      <View style={styles.ratingContainer}>
        <Text style={styles.star}>{'\u2605'}</Text>
        <Text style={styles.ratingText}>{item.rating.toFixed(1)}</Text>
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
    />
  );
}

const styles = StyleSheet.create({
  listContent: {
    padding: 16,
  },
  item: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  wineName: {
    flex: 1,
    fontSize: 16,
    color: '#000000',
    marginRight: 16,
  },
  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  star: {
    fontSize: 16,
    color: STAR_COLOR,
  },
  ratingText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#000000',
  },
  separator: {
    height: 1,
    backgroundColor: '#E0E0E0',
  },
});
