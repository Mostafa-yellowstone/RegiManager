import { useFonts } from 'expo-font';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { AuthProvider, useAuth } from '@/lib/auth';
import { Colors } from '@/constants/theme';

export { ErrorBoundary } from 'expo-router';

SplashScreen.preventAutoHideAsync();

function AuthGate({ children }: { children: React.ReactNode }) {
  const { ready, token, hasSeenOnboarding } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (!ready) return;
    const currentRoute = segments[0];

    // Persist session: logged-in users always land in the app.
    if (token) {
      if (currentRoute === 'login' || currentRoute === 'onboarding' || !currentRoute) {
        router.replace('/(tabs)');
      }
      return;
    }

    // Logged out: onboarding once, then login thereafter.
    if (!hasSeenOnboarding) {
      if (currentRoute !== 'onboarding') {
        router.replace('/onboarding');
      }
      return;
    }

    if (currentRoute !== 'login') {
      router.replace('/login');
    }
  }, [ready, token, hasSeenOnboarding, segments, router]);

  if (!ready) return null;

  return <>{children}</>;
}

export default function RootLayout() {
  const [loaded, error] = useFonts({
    SpaceMono: require('../assets/fonts/SpaceMono-Regular.ttf'),
  });

  useEffect(() => {
    if (error) throw error;
  }, [error]);

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  if (!loaded) return null;

  return (
    <AuthProvider>
      <StatusBar style="light" />
      <AuthGate>
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: Colors.navy },
            headerTintColor: Colors.white,
            headerTitleStyle: { fontWeight: '700', fontSize: 18 },
            headerShadowVisible: false,
            contentStyle: { backgroundColor: Colors.cream },
          }}
        >
          <Stack.Screen name="onboarding" options={{ headerShown: false }} />
          <Stack.Screen name="login" options={{ headerShown: false }} />
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen
            name="policy/[id]"
            options={{
              title: 'Policy Details',
              headerBackTitle: 'Back',
            }}
          />
          <Stack.Screen
            name="vehicle/[id]"
            options={{
              title: 'Vehicle',
              headerBackTitle: 'Back',
            }}
          />
        </Stack>
      </AuthGate>
    </AuthProvider>
  );
}
