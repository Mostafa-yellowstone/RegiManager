import '../global.css';

import { BottomSheetModalProvider } from '@gorhom/bottom-sheet';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useState, type ReactNode } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { AuthProvider, useAuth } from '@/lib/auth';
import { hasCompletedOnboarding } from '@/lib/onboarding';
import { Colors } from '@/lib/theme';

export { ErrorBoundary } from 'expo-router';

SplashScreen.preventAutoHideAsync();

function AuthGate({ children }: { children: ReactNode }) {
  const { ready, token } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const [onboardingReady, setOnboardingReady] = useState(false);
  const [seenOnboarding, setSeenOnboarding] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const done = await hasCompletedOnboarding();
      if (cancelled) return;
      setSeenOnboarding(done);
      setOnboardingReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Re-check after leaving onboarding so "Get started" / Skip unlocks login.
  useEffect(() => {
    if (segments[0] !== 'login' && segments[0] !== '(tabs)') return;
    let cancelled = false;
    (async () => {
      const done = await hasCompletedOnboarding();
      if (!cancelled && done) setSeenOnboarding(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [segments]);

  useEffect(() => {
    if (!ready || !onboardingReady) return;

    const root = segments[0];
    const onLogin = root === 'login';
    const onOnboarding = root === 'onboarding';

    if (!seenOnboarding && !onOnboarding) {
      router.replace('/onboarding');
      return;
    }

    if (seenOnboarding && !token && !onLogin) {
      router.replace('/login');
      return;
    }

    if (token && (onLogin || onOnboarding)) {
      router.replace('/(tabs)');
    }
  }, [ready, onboardingReady, seenOnboarding, token, segments, router]);

  if (!ready || !onboardingReady) return null;
  return <>{children}</>;
}

export default function RootLayout() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 20_000,
            retry: 1,
          },
        },
      }),
  );

  useEffect(() => {
    SplashScreen.hideAsync();
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BottomSheetModalProvider>
            <StatusBar style="light" />
            <AuthGate>
              <Stack
                screenOptions={{
                  headerStyle: { backgroundColor: Colors.navy },
                  headerTintColor: Colors.white,
                  headerTitleStyle: { fontWeight: '700' },
                  contentStyle: { backgroundColor: Colors.cream },
                }}
              >
                <Stack.Screen name="onboarding" options={{ headerShown: false, animation: 'fade' }} />
                <Stack.Screen name="login" options={{ headerShown: false }} />
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen
                  name="settings"
                  options={{ title: 'Settings', headerShown: true }}
                />
                <Stack.Screen
                  name="expense/[id]"
                  options={{ title: 'Expense detail', headerShown: true }}
                />
              </Stack>
            </AuthGate>
          </BottomSheetModalProvider>
        </AuthProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}
