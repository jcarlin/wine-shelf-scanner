import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { DebugData } from '../lib/types';
import { DebugStepRow } from './DebugStepRow';
import { colors, spacing, borderRadius } from '../lib/theme';

interface DebugTrayProps {
  debugData: DebugData;
}

export function DebugTray({ debugData }: DebugTrayProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <View style={[styles.container, expanded && styles.containerExpanded]}>
      <TouchableOpacity
        style={styles.header}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
        testID="debugTrayHeader"
      >
        <View style={styles.headerLeft}>
          <Ionicons name="build" size={16} color={colors.debugOrange} />
          <Text style={styles.headerTitle}>Debug</Text>
        </View>

        <View style={styles.statsContainer}>
          <View style={styles.statPill}>
            <Text style={styles.statText}>
              {debugData.texts_matched}/{debugData.total_ocr_texts}
            </Text>
          </View>
          {debugData.llm_calls_made > 0 && (
            <View style={styles.statPill}>
              <Text style={styles.statText}>
                LLM: {debugData.llm_calls_made}
              </Text>
            </View>
          )}
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={18}
            color={colors.textMuted}
          />
        </View>
      </TouchableOpacity>

      {expanded && (
        <ScrollView
          style={styles.content}
          contentContainerStyle={styles.contentContainer}
          showsVerticalScrollIndicator={true}
        >
          {/* Summary Stats */}
          <View style={styles.summaryRow}>
            <View style={styles.summaryItem}>
              <Text style={styles.summaryValue}>{debugData.total_ocr_texts}</Text>
              <Text style={styles.summaryLabel}>OCR Texts</Text>
            </View>
            <View style={styles.summaryItem}>
              <Text style={styles.summaryValue}>{debugData.bottles_detected}</Text>
              <Text style={styles.summaryLabel}>Bottles</Text>
            </View>
            <View style={styles.summaryItem}>
              <Text style={styles.summaryValue}>{debugData.texts_matched}</Text>
              <Text style={styles.summaryLabel}>Matched</Text>
            </View>
            <View style={styles.summaryItem}>
              <Text style={styles.summaryValue}>{debugData.llm_calls_made}</Text>
              <Text style={styles.summaryLabel}>LLM Calls</Text>
            </View>
          </View>

          {/* Pipeline Steps */}
          <Text style={styles.sectionTitle}>Pipeline Steps</Text>
          {debugData.pipeline_steps.map((step, index) => (
            <DebugStepRow key={index} step={step} index={index} />
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.debugBackground,
    borderRadius: borderRadius.md,
    marginHorizontal: spacing.sm,
    marginBottom: spacing.sm,
    overflow: 'hidden',
  },
  containerExpanded: {
    maxHeight: 350,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.debugHeaderBackground,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  headerTitle: {
    color: colors.textLight,
    fontSize: 14,
    fontWeight: '600',
  },
  statsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  statPill: {
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: 10,
  },
  statText: {
    color: colors.textLight,
    fontSize: 11,
    fontWeight: '500',
  },
  content: {
    flex: 1,
  },
  contentContainer: {
    paddingBottom: spacing.md,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.1)',
  },
  summaryItem: {
    alignItems: 'center',
  },
  summaryValue: {
    color: colors.textLight,
    fontSize: 18,
    fontWeight: '700',
  },
  summaryLabel: {
    color: colors.textMuted,
    fontSize: 10,
    marginTop: 2,
  },
  sectionTitle: {
    color: colors.debugOrange,
    fontSize: 12,
    fontWeight: '600',
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
});
