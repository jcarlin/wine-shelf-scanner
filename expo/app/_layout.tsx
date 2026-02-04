import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { FeatureFlagProvider } from '../lib/feature-flags';
import { colors } from '../lib/theme';

export default function RootLayout() {
  return (
    <FeatureFlagProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: {
            backgroundColor: colors.background,
          },
          headerTintColor: colors.textLight,
          headerTitleStyle: {
            fontWeight: '600',
          },
          contentStyle: {
            backgroundColor: colors.background,
          },
        }}
      >
        <Stack.Screen
          name="index"
          options={{
            title: 'Wine Scanner',
          }}
        />
      </Stack>
    </FeatureFlagProvider>
  );
}
