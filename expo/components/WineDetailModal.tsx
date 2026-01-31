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

interface WineDetailModalProps {
  visible: boolean;
  wine: WineResult | null;
  onClose: () => void;
}

const STAR_COLOR = '#FFCC00';
const WINE_COLOR = '#722F37';

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
    >
      <SafeAreaView style={styles.container}>
        <View style={styles.content}>
          <View style={styles.header}>
            <View style={styles.handleBar} />
          </View>

          <Text style={styles.wineName}>{wine.wine_name}</Text>

          {wine.rating !== null && (
            <View style={styles.ratingContainer}>
              <Text style={styles.star}>{'\u2605'}</Text>
              <Text style={styles.ratingText}>{wine.rating.toFixed(1)}</Text>
            </View>
          )}

          <Text style={styles.confidenceLabel}>{label}</Text>

          <TouchableOpacity
            style={styles.closeButton}
            onPress={onClose}
            activeOpacity={0.8}
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
    backgroundColor: '#FFFFFF',
  },
  content: {
    flex: 1,
    padding: 24,
    alignItems: 'center',
  },
  header: {
    width: '100%',
    alignItems: 'center',
    marginBottom: 24,
  },
  handleBar: {
    width: 36,
    height: 5,
    backgroundColor: '#E0E0E0',
    borderRadius: 2.5,
  },
  wineName: {
    fontSize: 24,
    fontWeight: '700',
    color: '#000000',
    textAlign: 'center',
    marginBottom: 24,
  },
  ratingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 16,
  },
  star: {
    fontSize: 48,
    color: STAR_COLOR,
  },
  ratingText: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#000000',
  },
  confidenceLabel: {
    fontSize: 15,
    color: '#666666',
    marginBottom: 32,
  },
  closeButton: {
    backgroundColor: WINE_COLOR,
    paddingVertical: 14,
    paddingHorizontal: 48,
    borderRadius: 12,
    marginTop: 'auto',
    marginBottom: 16,
  },
  closeButtonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
});
