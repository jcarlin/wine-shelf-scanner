import React from 'react';
import {
  View,
  Text,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';

const WINE_COLOR = '#722F37';

export function ProcessingSpinner() {
  return (
    <View style={styles.container} testID="processingSpinner">
      <ActivityIndicator size="large" color={WINE_COLOR} testID="processingIndicator" />
      <Text style={styles.text}>Analyzing wines...</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 16,
  },
  text: {
    fontSize: 17,
    color: '#333333',
    fontWeight: '500',
  },
});
