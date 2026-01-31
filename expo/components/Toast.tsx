import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  Animated,
  StyleSheet,
} from 'react-native';
import { colors, spacing, borderRadius, fontSize, animation, layout } from '../lib/theme';

interface ToastProps {
  message: string;
  visible: boolean;
}

export function Toast({ message, visible }: ToastProps) {
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(opacity, {
      toValue: visible ? 1 : 0,
      duration: animation.toastDuration,
      useNativeDriver: true,
    }).start();
  }, [visible]);

  return (
    <Animated.View style={[styles.container, { opacity }]} pointerEvents="none" testID="toast">
      <View style={styles.toast} testID="toastContent">
        <Text style={styles.message} testID="toastMessage">{message}</Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    bottom: layout.toastBottomPosition,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  toast: {
    backgroundColor: colors.toastBackground,
    paddingVertical: spacing.sm + spacing.xs,
    paddingHorizontal: spacing.lg,
    borderRadius: borderRadius.sm,
    maxWidth: '80%',
  },
  message: {
    color: colors.textLight,
    fontSize: fontSize.sm,
    textAlign: 'center',
  },
});
