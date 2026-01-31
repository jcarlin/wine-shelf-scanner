import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
} from 'react-native';

interface CameraCaptureProps {
  onCapture: () => void;
  onSelectFromLibrary: () => void;
}

const WINE_COLOR = '#722F37';

export function CameraCapture({ onCapture, onSelectFromLibrary }: CameraCaptureProps) {
  return (
    <View style={styles.container}>
      <TouchableOpacity
        style={styles.button}
        onPress={onCapture}
        activeOpacity={0.8}
      >
        <Text style={styles.buttonText}>Take Photo</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.button}
        onPress={onSelectFromLibrary}
        activeOpacity={0.8}
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
    gap: 16,
    paddingHorizontal: 32,
  },
  button: {
    backgroundColor: WINE_COLOR,
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 12,
    width: '100%',
    alignItems: 'center',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '600',
  },
});
