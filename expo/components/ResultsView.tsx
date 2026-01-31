import React, { useState, useEffect } from 'react';
import {
  View,
  Image,
  StyleSheet,
  LayoutChangeEvent,
} from 'react-native';
import { ScanResponse, Size } from '../lib/types';
import { OverlayContainer } from './OverlayContainer';
import { Toast } from './Toast';

interface ResultsViewProps {
  response: ScanResponse;
  imageUri: string;
}

export function ResultsView({ response, imageUri }: ResultsViewProps) {
  const [containerSize, setContainerSize] = useState<Size | null>(null);
  const [imageSize, setImageSize] = useState<Size | null>(null);
  const [showToast, setShowToast] = useState(false);

  // Check for partial detection (some results AND some fallback)
  const isPartialDetection =
    response.results.length > 0 && response.fallback_list.length > 0;

  useEffect(() => {
    if (isPartialDetection) {
      setShowToast(true);
      const timer = setTimeout(() => setShowToast(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isPartialDetection]);

  // Get image dimensions
  useEffect(() => {
    Image.getSize(
      imageUri,
      (width, height) => {
        setImageSize({ width, height });
      },
      (error) => {
        console.error('Failed to get image size:', error);
        // Fallback to a default aspect ratio
        setImageSize({ width: 3, height: 4 });
      }
    );
  }, [imageUri]);

  const handleLayout = (event: LayoutChangeEvent) => {
    const { width, height } = event.nativeEvent.layout;
    setContainerSize({ width, height });
  };

  const canRenderOverlays = containerSize && imageSize;

  return (
    <View style={styles.container} onLayout={handleLayout}>
      <Image
        source={{ uri: imageUri }}
        style={styles.image}
        resizeMode="contain"
      />

      {canRenderOverlays && (
        <OverlayContainer
          results={response.results}
          imageSize={imageSize}
          containerSize={containerSize}
        />
      )}

      <Toast
        message="Some bottles couldn't be recognized"
        visible={showToast}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    position: 'relative',
  },
  image: {
    flex: 1,
    width: '100%',
    height: '100%',
  },
});
