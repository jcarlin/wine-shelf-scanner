import React, { useState } from 'react';
import {
  View,
  Text,
  Modal,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  ScrollView,
} from 'react-native';
import { WineResult } from '../lib/types';
import { useFeatureFlags } from '../lib/feature-flags';
import { useWineMemory } from '../hooks/useWineMemory';
import { confidenceLabel } from '../lib/overlay-math';
import { colors, spacing, borderRadius, fontSize, layout } from '../lib/theme';

interface WineDetailModalProps {
  visible: boolean;
  wine: WineResult | null;
  onClose: () => void;
  shelfRank?: number;
  shelfTotal?: number;
}

/** Maps wine type to display color */
const wineTypeColors: Record<string, string> = {
  Red: '#8B0000',
  White: '#F5DEB3',
  Rosé: '#FFB6C1',
  Sparkling: '#FFD700',
  Dessert: '#DAA520',
  Fortified: '#8B4513',
};

/** Gets contrasting text color for wine type badge */
function getWineTypeTextColor(wineType: string): string {
  const darkTextTypes = ['White', 'Sparkling', 'Rosé'];
  return darkTextTypes.includes(wineType) ? '#333333' : '#FFFFFF';
}

/** Formats review count (e.g., 12500 -> "12.5K reviews") */
function formatReviewCount(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1).replace(/\.0$/, '')}K reviews`;
  }
  return `${count} reviews`;
}

export function WineDetailModal({ visible, wine, onClose, shelfRank, shelfTotal }: WineDetailModalProps) {
  const flags = useFeatureFlags();
  const memory = useWineMemory();
  const [feedbackGiven, setFeedbackGiven] = useState(false);

  if (!wine) {
    return null;
  }

  const existingSentiment = flags.wineMemory ? memory.get(wine.wine_name) : undefined;

  const label = confidenceLabel(wine.confidence);
  const hasMetadata = wine.wine_type || wine.brand || wine.region || wine.varietal || wine.blurb;
  const hasReviews = wine.review_count || (wine.review_snippets && wine.review_snippets.length > 0);

  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
      testID="wineDetailSheet"
    >
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <View style={styles.handleBar} />
        </View>

        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.content} testID="wineDetailContent">
            {/* Wine Type Badge */}
            {wine.wine_type && (
              <View
                style={[
                  styles.wineTypeBadge,
                  { backgroundColor: wineTypeColors[wine.wine_type] || colors.wine },
                ]}
              >
                <Text
                  style={[
                    styles.wineTypeText,
                    { color: getWineTypeTextColor(wine.wine_type) },
                  ]}
                >
                  {wine.wine_type}
                </Text>
              </View>
            )}

            {/* Wine Name */}
            <Text style={styles.wineName} testID="detailSheetWineName">
              {wine.wine_name}
            </Text>

            {/* Brand/Winery */}
            {wine.brand && (
              <Text style={styles.brand}>by {wine.brand}</Text>
            )}

            {/* Rating */}
            {wine.rating !== null && (
              <View style={styles.ratingContainer} testID="detailSheetRating">
                <Text style={styles.star}>{'\u2605'}</Text>
                <Text style={styles.ratingText}>{wine.rating.toFixed(1)}</Text>
              </View>
            )}

            {/* Review Count */}
            {wine.review_count && wine.review_count > 0 && (
              <Text style={styles.reviewCount}>
                {formatReviewCount(wine.review_count)}
              </Text>
            )}

            {/* Confidence Label */}
            <Text style={styles.confidenceLabel} testID="detailSheetConfidence">
              {label}
            </Text>

            {/* Safe Pick Badge */}
            {flags.safePick && wine.is_safe_pick && (
              <View style={styles.safePickBadge}>
                <Text style={styles.safePickText}>{'\u2713'} Crowd favorite</Text>
              </View>
            )}

            {/* Shelf Ranking */}
            {flags.shelfRanking && shelfRank !== undefined && shelfTotal !== undefined && (
              <Text style={[styles.rankLabel, shelfRank === 1 && styles.rankLabelTop]}>
                {shelfRank === 1 ? 'Best on this shelf' : `Ranked #${shelfRank} of ${shelfTotal} on this shelf`}
              </Text>
            )}

            {/* Divider */}
            {(hasMetadata || hasReviews) && <View style={styles.divider} />}

            {/* Region & Varietal */}
            {(wine.region || wine.varietal) && (
              <View style={styles.detailsRow}>
                {wine.region && (
                  <View style={styles.detailItem}>
                    <Text style={styles.detailLabel}>Region</Text>
                    <Text style={styles.detailValue}>{wine.region}</Text>
                  </View>
                )}
                {wine.varietal && (
                  <View style={styles.detailItem}>
                    <Text style={styles.detailLabel}>Varietal</Text>
                    <Text style={styles.detailValue}>{wine.varietal}</Text>
                  </View>
                )}
              </View>
            )}

            {/* Blurb/Description */}
            {wine.blurb && (
              <View style={styles.blurbContainer}>
                <Text style={styles.blurb}>"{wine.blurb}"</Text>
              </View>
            )}

            {/* Food Pairing */}
            {flags.pairings && wine.pairing && (
              <View style={styles.pairingContainer}>
                <Text style={styles.pairingLabel}>{'\uD83C\uDF74'} Goes with</Text>
                <Text style={styles.pairingText}>{wine.pairing}</Text>
              </View>
            )}

            {/* Wine Memory Banner */}
            {flags.wineMemory && existingSentiment && !feedbackGiven && (
              <View style={[
                styles.memoryBanner,
                { backgroundColor: existingSentiment === 'liked' ? '#E8F5E9' : '#FFEBEE' },
              ]}>
                <Text style={styles.memoryBannerText}>
                  {existingSentiment === 'liked' ? '\u2665 You liked this wine' : '\u2715 You didn\'t like this wine'}
                </Text>
                <TouchableOpacity onPress={() => { memory.clear(wine.wine_name); }}>
                  <Text style={styles.memoryUndoText}>Undo</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Feedback Section */}
            {flags.wineMemory && (
              <View style={styles.feedbackSection}>
                {feedbackGiven ? (
                  <Text style={styles.feedbackThanks}>{'\u2713'} Thanks for your feedback!</Text>
                ) : (
                  <View style={styles.feedbackPrompt}>
                    <Text style={styles.feedbackPromptText}>Is this the right wine?</Text>
                    <View style={styles.feedbackButtons}>
                      <TouchableOpacity
                        style={styles.feedbackButton}
                        onPress={() => {
                          memory.save(wine.wine_name, 'liked');
                          setFeedbackGiven(true);
                        }}
                        testID="thumbsUpButton"
                      >
                        <Text style={styles.feedbackButtonIcon}>{'\uD83D\uDC4D'}</Text>
                        <Text style={styles.feedbackButtonLabel}>Yes</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={styles.feedbackButton}
                        onPress={() => {
                          memory.save(wine.wine_name, 'disliked');
                          setFeedbackGiven(true);
                        }}
                        testID="thumbsDownButton"
                      >
                        <Text style={styles.feedbackButtonIcon}>{'\uD83D\uDC4E'}</Text>
                        <Text style={styles.feedbackButtonLabel}>No</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </View>
            )}

            {/* Review Snippets */}
            {wine.review_snippets && wine.review_snippets.length > 0 && (
              <View style={styles.reviewsContainer}>
                <Text style={styles.reviewsTitle}>What people say</Text>
                {wine.review_snippets.map((snippet, index) => (
                  <View key={index} style={styles.reviewSnippet}>
                    <Text style={styles.reviewQuote}>"{snippet}"</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        </ScrollView>

        {/* Close Button (fixed at bottom) */}
        <View style={styles.buttonContainer}>
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
  header: {
    width: '100%',
    alignItems: 'center',
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  handleBar: {
    width: layout.handleBarWidth,
    height: layout.handleBarHeight,
    backgroundColor: colors.handleBar,
    borderRadius: borderRadius.xs,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    flex: 1,
    padding: spacing.lg,
    alignItems: 'center',
  },
  wineTypeBadge: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.md,
    marginBottom: spacing.md,
  },
  wineTypeText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  wineName: {
    fontSize: fontSize.xxl,
    fontWeight: '700',
    color: colors.textDark,
    textAlign: 'center',
    marginBottom: spacing.xs,
  },
  brand: {
    fontSize: fontSize.md,
    color: colors.textSecondary,
    textAlign: 'center',
    marginBottom: spacing.md,
    fontStyle: 'italic',
  },
  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.xs,
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
  reviewCount: {
    fontSize: fontSize.sm,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  confidenceLabel: {
    fontSize: fontSize.sm,
    color: colors.textMuted,
    marginBottom: spacing.md,
  },
  divider: {
    width: '80%',
    height: 1,
    backgroundColor: colors.separator,
    marginVertical: spacing.md,
  },
  detailsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.xl,
    marginBottom: spacing.md,
    width: '100%',
  },
  detailItem: {
    alignItems: 'center',
  },
  detailLabel: {
    fontSize: 12,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  detailValue: {
    fontSize: fontSize.md,
    color: colors.textDark,
    fontWeight: '500',
  },
  blurbContainer: {
    backgroundColor: '#F8F8F8',
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginVertical: spacing.md,
    width: '100%',
  },
  blurb: {
    fontSize: fontSize.md,
    color: colors.textSecondary,
    fontStyle: 'italic',
    textAlign: 'center',
    lineHeight: 22,
  },
  reviewsContainer: {
    width: '100%',
    marginTop: spacing.md,
  },
  reviewsTitle: {
    fontSize: fontSize.md,
    fontWeight: '600',
    color: colors.textDark,
    marginBottom: spacing.sm,
  },
  reviewSnippet: {
    backgroundColor: '#FAFAFA',
    borderLeftWidth: 3,
    borderLeftColor: colors.star,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
    borderRadius: borderRadius.sm,
  },
  reviewQuote: {
    fontSize: fontSize.sm,
    color: colors.textSecondary,
    fontStyle: 'italic',
    lineHeight: 20,
  },
  buttonContainer: {
    padding: spacing.lg,
    paddingBottom: spacing.md,
  },
  closeButton: {
    backgroundColor: colors.wine,
    paddingVertical: 14,
    paddingHorizontal: spacing.xxl,
    borderRadius: borderRadius.md,
    alignItems: 'center',
  },
  closeButtonText: {
    color: colors.textLight,
    fontSize: fontSize.lg,
    fontWeight: '600',
  },
  safePickBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E8F5E9',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borderRadius.md,
    marginBottom: spacing.sm,
  },
  safePickText: {
    fontSize: fontSize.sm,
    fontWeight: '600',
    color: '#2E7D32',
  },
  rankLabel: {
    fontSize: fontSize.sm,
    fontWeight: '500',
    color: colors.textSecondary,
    marginBottom: spacing.sm,
  },
  rankLabelTop: {
    color: '#D4A017',
    fontWeight: '600',
  },
  pairingContainer: {
    backgroundColor: '#FBF8F0',
    borderRadius: borderRadius.md,
    padding: spacing.md,
    marginVertical: spacing.sm,
    width: '100%',
  },
  pairingLabel: {
    fontSize: fontSize.sm,
    color: colors.textSecondary,
    marginBottom: 4,
  },
  pairingText: {
    fontSize: fontSize.md,
    color: colors.textDark,
    fontWeight: '500',
  },
  memoryBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borderRadius.md,
    marginBottom: spacing.sm,
    width: '100%',
  },
  memoryBannerText: {
    fontSize: fontSize.sm,
    color: colors.textSecondary,
  },
  memoryUndoText: {
    fontSize: fontSize.sm,
    color: '#2196F3',
    fontWeight: '500',
  },
  feedbackSection: {
    paddingTop: spacing.sm,
    alignItems: 'center',
    width: '100%',
  },
  feedbackPrompt: {
    alignItems: 'center',
    gap: spacing.sm,
  },
  feedbackPromptText: {
    fontSize: fontSize.sm,
    color: colors.textSecondary,
  },
  feedbackButtons: {
    flexDirection: 'row',
    gap: spacing.xl,
  },
  feedbackButton: {
    alignItems: 'center',
    gap: 4,
  },
  feedbackButtonIcon: {
    fontSize: 28,
  },
  feedbackButtonLabel: {
    fontSize: 12,
    color: colors.textSecondary,
  },
  feedbackThanks: {
    fontSize: fontSize.sm,
    color: '#4CAF50',
    fontWeight: '500',
  },
});
