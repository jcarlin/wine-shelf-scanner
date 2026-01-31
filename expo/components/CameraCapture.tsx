import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';
import { colors, spacing, borderRadius, fontSize } from '../lib/theme';

interface CameraCaptureProps {
  onCapture: () => void;
  onSelectFromLibrary: () => void;
}

export function CameraCapture({ onCapture, onSelectFromLibrary }: CameraCaptureProps) {
  return (
    <View style={styles.container} testID="cameraCapture">
      <TouchableOpacity
        style={styles.button}
        onPress={onCapture}
        activeOpacity={0.8}
        testID="scanShelfButton"
      >
        <Text style={styles.buttonText}>Take Photo</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.button}
        onPress={onSelectFromLibrary}
        activeOpacity={0.8}
        testID="choosePhotoButton"
      >
        <Text style={styles.buttonText}>Choose from Library</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
  },
  button: {
    backgroundColor: colors.wine,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xl,
    borderRadius: borderRadius.md,
    width: '100%',
    alignItems: 'center',
  },
  buttonText: {
    color: colors.textLight,
    fontSize: fontSize.lg,
    fontWeight: '600',
  },
});
