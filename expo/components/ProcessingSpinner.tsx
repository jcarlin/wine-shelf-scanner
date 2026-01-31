import React from 'react';
import {
  View,
  Text,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import { colors, spacing, fontSize } from '../lib/theme';

export function ProcessingSpinner() {
  return (
    <View style={styles.container} testID="processingSpinner">
      <ActivityIndicator size="large" color={colors.wine} testID="processingIndicator" />
      <Text style={styles.text}>Analyzing wines...</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
  },
  text: {
    fontSize: fontSize.lg,
    color: colors.textProcessing,
    fontWeight: '500',
  },
});
