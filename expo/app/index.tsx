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

const WINE_COLOR = '#722F37';
const BACKGROUND_COLOR = '#1a1a2e';

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
            <View style={styles.resultsContainer}>
              <FallbackList wines={state.response.fallback_list} />
              <View style={styles.buttonContainer}>
                <TouchableOpacity
                  style={styles.button}
                  onPress={reset}
                  activeOpacity={0.8}
                >
                  <Text style={styles.buttonText}>Scan Another</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        }

        // Success (with or without partial detection)
        return (
          <View style={styles.resultsContainer}>
            <ResultsView
              response={state.response}
              imageUri={state.imageUri}
            />
            <View style={styles.buttonContainer}>
              <TouchableOpacity
                style={styles.button}
                onPress={reset}
                activeOpacity={0.8}
              >
                <Text style={styles.buttonText}>Scan Another</Text>
              </TouchableOpacity>
            </View>
          </View>
        );
      }

      case 'error':
        return (
          <View style={styles.errorContainer}>
            <Text style={styles.errorTitle}>Something went wrong</Text>
            <Text style={styles.errorMessage}>{state.message}</Text>
            <TouchableOpacity
              style={styles.button}
              onPress={reset}
              activeOpacity={0.8}
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
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {renderContent()}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BACKGROUND_COLOR,
  },
  resultsContainer: {
    flex: 1,
  },
  buttonContainer: {
    padding: 16,
    paddingBottom: 8,
  },
  button: {
    backgroundColor: WINE_COLOR,
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 12,
    alignItems: 'center',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  errorTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 12,
    textAlign: 'center',
  },
  errorMessage: {
    fontSize: 16,
    color: '#999999',
    marginBottom: 32,
    textAlign: 'center',
  },
});
