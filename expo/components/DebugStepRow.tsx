import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DebugPipelineStep } from '../lib/types';
import { colors, spacing, borderRadius, fontSize } from '../lib/theme';

interface DebugStepRowProps {
  step: DebugPipelineStep;
  index: number;
}

export function DebugStepRow({ step, index }: DebugStepRowProps) {
  const [expanded, setExpanded] = useState(false);

  const getStatusIcon = () => {
    if (step.step_failed) {
      return <Ionicons name="close-circle" size={16} color={colors.statusFailure} />;
    }
    if (step.included_in_results) {
      return <Ionicons name="checkmark-circle" size={16} color={colors.statusSuccess} />;
    }
    return <Ionicons name="warning" size={16} color={colors.statusWarning} />;
  };

  const getMatchedName = () => {
    if (step.final_result?.wine_name) {
      return step.final_result.wine_name;
    }
    if (step.step_failed) {
      return 'No match found';
    }
    return 'Below threshold';
  };

  const getWeightedScore = () => {
    if (step.fuzzy_match?.scores?.weighted_score) {
      return `${Math.round(step.fuzzy_match.scores.weighted_score * 100)}%`;
    }
    if (step.final_result?.confidence) {
      return `${Math.round(step.final_result.confidence * 100)}%`;
    }
    return '—';
  };

  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={styles.headerLeft}>
          {getStatusIcon()}
          <Text style={styles.indexText}>#{index + 1}</Text>
          <Text style={styles.normalizedText} numberOfLines={1}>
            {step.normalized_text || step.raw_text}
          </Text>
        </View>
        <View style={styles.headerRight}>
          <Text style={styles.matchedName} numberOfLines={1}>
            {getMatchedName()}
          </Text>
          <Text style={styles.scoreText}>{getWeightedScore()}</Text>
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={16}
            color={colors.textMuted}
          />
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.details}>
          {/* Raw OCR Text */}
          <View style={styles.detailSection}>
            <Text style={styles.detailLabel}>Raw OCR:</Text>
            <Text style={styles.detailValue}>{step.raw_text}</Text>
          </View>

          {/* Normalized Text */}
          <View style={styles.detailSection}>
            <Text style={styles.detailLabel}>Normalized:</Text>
            <Text style={styles.detailValue}>{step.normalized_text}</Text>
          </View>

          {/* Fuzzy Match Scores */}
          {step.fuzzy_match && (
            <View style={styles.detailSection}>
              <Text style={styles.detailLabel}>Fuzzy Match:</Text>
              <Text style={styles.detailValue}>
                Candidate: {step.fuzzy_match.candidate}
              </Text>
              <View style={styles.scoresTable}>
                <View style={styles.scoreRow}>
                  <Text style={styles.scoreLabel}>Ratio:</Text>
                  <Text style={styles.scoreValue}>
                    {Math.round(step.fuzzy_match.scores.ratio * 100)}%
                  </Text>
                </View>
                <View style={styles.scoreRow}>
                  <Text style={styles.scoreLabel}>Partial:</Text>
                  <Text style={styles.scoreValue}>
                    {Math.round(step.fuzzy_match.scores.partial_ratio * 100)}%
                  </Text>
                </View>
                <View style={styles.scoreRow}>
                  <Text style={styles.scoreLabel}>Token Sort:</Text>
                  <Text style={styles.scoreValue}>
                    {Math.round(step.fuzzy_match.scores.token_sort_ratio * 100)}%
                  </Text>
                </View>
                <View style={styles.scoreRow}>
                  <Text style={styles.scoreLabel}>Phonetic Bonus:</Text>
                  <Text style={styles.scoreValue}>
                    +{Math.round(step.fuzzy_match.scores.phonetic_bonus * 100)}%
                  </Text>
                </View>
                <View style={[styles.scoreRow, styles.weightedRow]}>
                  <Text style={styles.weightedLabel}>Weighted:</Text>
                  <Text style={styles.weightedValue}>
                    {Math.round(step.fuzzy_match.scores.weighted_score * 100)}%
                  </Text>
                </View>
              </View>
            </View>
          )}

          {/* LLM Validation */}
          {step.llm_validation && (
            <View style={styles.detailSection}>
              <Text style={styles.detailLabel}>LLM Validation:</Text>
              <View style={styles.llmResult}>
                <Text style={styles.detailValue}>
                  {step.llm_validation.is_valid_match ? '✓ Valid' : '✗ Invalid'}
                  {step.llm_validation.wine_name && `: ${step.llm_validation.wine_name}`}
                </Text>
                {step.llm_validation.confidence && (
                  <Text style={styles.detailValue}>
                    Confidence: {Math.round(step.llm_validation.confidence * 100)}%
                  </Text>
                )}
                {step.llm_validation.reasoning && (
                  <Text style={styles.reasoningText}>
                    {step.llm_validation.reasoning}
                  </Text>
                )}
              </View>
            </View>
          )}

          {/* Final Result */}
          {step.final_result && (
            <View style={styles.detailSection}>
              <Text style={styles.detailLabel}>Final Result:</Text>
              <Text style={styles.detailValue}>
                {step.final_result.wine_name}
              </Text>
              <Text style={styles.detailValue}>
                Confidence: {Math.round(step.final_result.confidence * 100)}% (source: {step.final_result.source})
              </Text>
            </View>
          )}

          {/* Bottle Index */}
          {step.bottle_index !== null && (
            <View style={styles.detailSection}>
              <Text style={styles.detailLabel}>Bottle Index:</Text>
              <Text style={styles.detailValue}>{step.bottle_index}</Text>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.1)',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: spacing.xs,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
    justifyContent: 'flex-end',
  },
  indexText: {
    color: colors.textMuted,
    fontSize: 12,
    fontWeight: '500',
  },
  normalizedText: {
    color: colors.textLight,
    fontSize: 13,
    flex: 1,
  },
  matchedName: {
    color: colors.textMuted,
    fontSize: 12,
    maxWidth: 100,
  },
  scoreText: {
    color: colors.statusSuccess,
    fontSize: 12,
    fontWeight: '600',
    minWidth: 35,
    textAlign: 'right',
  },
  details: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  detailSection: {
    marginTop: spacing.sm,
  },
  detailLabel: {
    color: colors.debugOrange,
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 2,
  },
  detailValue: {
    color: colors.textLight,
    fontSize: 12,
  },
  scoresTable: {
    marginTop: spacing.xs,
    backgroundColor: 'rgba(0, 0, 0, 0.3)',
    borderRadius: borderRadius.sm,
    padding: spacing.sm,
  },
  scoreRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 2,
  },
  scoreLabel: {
    color: colors.textMuted,
    fontSize: 11,
  },
  scoreValue: {
    color: colors.textLight,
    fontSize: 11,
  },
  weightedRow: {
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.2)',
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
  },
  weightedLabel: {
    color: colors.debugOrange,
    fontSize: 11,
    fontWeight: '600',
  },
  weightedValue: {
    color: colors.debugOrange,
    fontSize: 11,
    fontWeight: '600',
  },
  llmResult: {
    marginTop: spacing.xs,
  },
  reasoningText: {
    color: colors.textMuted,
    fontSize: 11,
    fontStyle: 'italic',
    marginTop: spacing.xs,
  },
});
