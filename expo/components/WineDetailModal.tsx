import React from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
} from 'react-native';
import { WineResult } from '../lib/types';
import { confidenceLabel } from '../lib/overlay-math';
import { colors, spacing, borderRadius, fontSize, layout } from '../lib/theme';

interface WineDetailModalProps {
  visible: boolean;
  wine: WineResult | null;
  onClose: () => void;
}

export function WineDetailModal({ visible, wine, onClose }: WineDetailModalProps) {
  if (!wine) {
    return null;
  }

  const label = confidenceLabel(wine.confidence);

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
      testID="wineDetailSheet"
    >
      <SafeAreaView style={styles.container}>
        <View style={styles.content} testID="wineDetailContent">
          <View style={styles.header}>
            <View style={styles.handleBar} />
          </View>

          <Text style={styles.wineName} testID="detailSheetWineName">{wine.wine_name}</Text>

          {wine.rating !== null && (
            <View style={styles.ratingContainer} testID="detailSheetRating">
              <Text style={styles.star}>{'\u2605'}</Text>
              <Text style={styles.ratingText}>{wine.rating.toFixed(1)}</Text>
            </View>
          )}

          <Text style={styles.confidenceLabel} testID="detailSheetConfidence">{label}</Text>

          <TouchableOpacity
            style={styles.closeButton}
            onPress={onClose}
            activeOpacity={0.8}
            testID="detailSheetCloseButton"
          >
            <Text style={styles.closeButtonText}>Close</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.sheetBackground,
  },
  content: {
    flex: 1,
    padding: spacing.lg,
    alignItems: 'center',
  },
  header: {
    width: '100%',
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  handleBar: {
    width: layout.handleBarWidth,
    height: layout.handleBarHeight,
    backgroundColor: colors.handleBar,
    borderRadius: borderRadius.xs,
  },
  wineName: {
    fontSize: fontSize.xxl,
    fontWeight: '700',
    color: colors.textDark,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },
  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  star: {
    fontSize: fontSize.rating,
    color: colors.star,
  },
  ratingText: {
    fontSize: fontSize.rating,
    fontWeight: 'bold',
    color: colors.textDark,
  },
  confidenceLabel: {
    fontSize: fontSize.sm,
    color: colors.textSecondary,
    marginBottom: spacing.xl,
  },
  closeButton: {
    backgroundColor: colors.wine,
    paddingVertical: 14,
    paddingHorizontal: spacing.xxl,
    borderRadius: borderRadius.md,
    marginTop: 'auto',
    marginBottom: spacing.md,
  },
  closeButtonText: {
    color: colors.textLight,
    fontSize: fontSize.lg,
    fontWeight: '600',
  },
});
