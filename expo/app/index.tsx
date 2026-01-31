import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useScanState } from '../hooks/useScanState';
import { CameraCapture } from '../components/CameraCapture';
import { ProcessingSpinner } from '../components/ProcessingSpinner';
import { ResultsView } from '../components/ResultsView';
import { FallbackList } from '../components/FallbackList';
import { colors, spacing, borderRadius, fontSize } from '../lib/theme';

export default function ScannerScreen() {
  const { state, pickAndScan, pickFromLibrary, reset } = useScanState();

  const renderContent = () => {
    switch (state.status) {
      case 'idle':
        return (
          <CameraCapture
            onCapture={pickAndScan}
            onSelectFromLibrary={pickFromLibrary}
          />
        );

      case 'processing':
        return <ProcessingSpinner />;

      case 'results': {
        const hasResults = state.response.results.length > 0;
        const hasFallback = state.response.fallback_list.length > 0;
        const isFullFailure = !hasResults && hasFallback;

        if (isFullFailure) {
          // Full failure: show fallback list
          return (
            <View style={styles.resultsContainer} testID="fallbackContainer">
              <FallbackList wines={state.response.fallback_list} />
              <View style={styles.buttonContainer}>
                <TouchableOpacity
                  style={styles.button}
                  onPress={reset}
                  activeOpacity={0.8}
                  testID="scanAnotherButton"
                >
                  <Text style={styles.buttonText}>Scan Another</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        }

        // Success (with or without partial detection)
        return (
          <View style={styles.resultsContainer} testID="successContainer">
            <ResultsView
              response={state.response}
              imageUri={state.imageUri}
            />
            <View style={styles.buttonContainer}>
              <TouchableOpacity
                style={styles.button}
                onPress={reset}
                activeOpacity={0.8}
                testID="scanAnotherButton"
              >
                <Text style={styles.buttonText}>Scan Another</Text>
              </TouchableOpacity>
            </View>
          </View>
        );
      }

      case 'error':
        return (
          <View style={styles.errorContainer} testID="errorView">
            <Text style={styles.errorTitle} testID="errorTitle">Something went wrong</Text>
            <Text style={styles.errorMessage} testID="errorMessage">{state.message}</Text>
            <TouchableOpacity
              style={styles.button}
              onPress={reset}
              activeOpacity={0.8}
              testID="retryButton"
            >
              <Text style={styles.buttonText}>Try Again</Text>
            </TouchableOpacity>
          </View>
        );

      default:
        return null;
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']} testID="scannerScreen">
      {renderContent()}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  resultsContainer: {
    flex: 1,
  },
  buttonContainer: {
    padding: spacing.md,
    paddingBottom: spacing.sm,
  },
  button: {
    backgroundColor: colors.wine,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: borderRadius.md,
    alignItems: 'center',
  },
  buttonText: {
    color: colors.textLight,
    fontSize: fontSize.lg,
    fontWeight: '600',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  errorTitle: {
    fontSize: fontSize.xl,
    fontWeight: '700',
    color: colors.textLight,
    marginBottom: spacing.sm + spacing.xs,
    textAlign: 'center',
  },
  errorMessage: {
    fontSize: fontSize.md,
    color: colors.textMuted,
    marginBottom: spacing.xl,
    textAlign: 'center',
  },
});
