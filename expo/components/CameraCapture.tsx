import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borderRadius, fontSize } from '../lib/theme';

interface CameraCaptureProps {
  onCapture: () => void;
  onSelectFromLibrary: () => void;
}

export function CameraCapture({ onCapture, onSelectFromLibrary }: CameraCaptureProps) {
  return (
    <View style={styles.container} testID="cameraCapture">
      {/* Hero section */}
      <View style={styles.heroSection}>
        <Ionicons
          name="scan-outline"
          size={80}
          color="rgba(255, 255, 255, 0.7)"
        />
        <Text style={styles.heroTitle}>Point at a wine shelf</Text>
        <Text style={styles.heroSubtitle}>Take a photo to see ratings</Text>
      </View>

      {/* Button section */}
      <View style={styles.buttonSection}>
        <TouchableOpacity
          style={styles.primaryButton}
          onPress={onCapture}
          activeOpacity={0.8}
          testID="scanShelfButton"
        >
          <Ionicons name="camera" size={20} color={colors.buttonPrimaryText} />
          <Text style={styles.primaryButtonText}>Scan Shelf</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.secondaryButton}
          onPress={onSelectFromLibrary}
          activeOpacity={0.8}
          testID="choosePhotoButton"
        >
          <Ionicons name="images" size={20} color={colors.buttonSecondaryText} />
          <Text style={styles.secondaryButtonText}>Choose Photo</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
  },
  heroSection: {
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  heroTitle: {
    fontSize: fontSize.xl,
    fontWeight: '600',
    color: colors.textLight,
    marginTop: spacing.lg,
  },
  heroSubtitle: {
    fontSize: fontSize.sm,
    color: 'rgba(255, 255, 255, 0.6)',
    marginTop: spacing.sm,
  },
  buttonSection: {
    width: '100%',
    gap: 12,
    marginTop: spacing.md,
  },
  primaryButton: {
    backgroundColor: colors.buttonPrimaryBackground,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.md,
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  primaryButtonText: {
    color: colors.buttonPrimaryText,
    fontSize: fontSize.lg,
    fontWeight: '600',
  },
  secondaryButton: {
    backgroundColor: colors.buttonSecondaryBackground,
    paddingVertical: spacing.md,
    borderRadius: borderRadius.md,
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  secondaryButtonText: {
    color: colors.buttonSecondaryText,
    fontSize: fontSize.lg,
    fontWeight: '600',
  },
});
