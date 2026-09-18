import '../global.css';

import {
  Manrope_400Regular,
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/manrope';
import { BottomSheetModalProvider } from '@gorhom/bottom-sheet';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useState, type ReactNode } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';
import 'react-native-reanimated';

import { AuthProvider, useAuth } from '@/lib/auth';
import { hasCompletedOnboarding, subscribeOnboarding } from '@/lib/onboarding';
import { registerSnapshotNotificationHandler } from '@/lib/notifications';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';

export { ErrorBoundary } from 'expo-router';

SplashScreen.preventAutoHideAsync();

function AuthGate({ children }: { children: ReactNode }) {
  const { ready, token } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const setPreset = useDateRangeStore((s) => s.setPreset);
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

  useEffect(() => subscribeOnboarding((done) => setSeenOnboarding(done)), []);

  useEffect(() => {
    if (ready && onboardingReady) {
      void SplashScreen.hideAsync();
    }
  }, [ready, onboardingReady]);

  useEffect(() => {
    if (!ready || !onboardingReady || !token) return;
    let active = true;
    let unsubscribe: (() => void) | undefined;
    void registerSnapshotNotificationHandler(() => {
      if (!active) return;
      setPreset('yesterday');
      router.replace('/(tabs)');
    }).then((fn) => {
      unsubscribe = fn;
    });
    return () => {
      active = false;
      unsubscribe?.();
    };
  }, [ready, onboardingReady, token, router, setPreset]);

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

  if (!ready || !onboardingReady) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: Colors.navy,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <ActivityIndicator color={Colors.teal} size="large" />
      </View>
    );
  }
  return <>{children}</>;
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    Manrope_400Regular,
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
  });

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

  if (!fontsLoaded) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: Colors.navy,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <ActivityIndicator color={Colors.teal} size="large" />
      </View>
    );
  }

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
                  headerTitleStyle: { fontFamily: Fonts.bold, fontWeight: '700' },
                  contentStyle: { backgroundColor: Colors.cream },
                }}
              >
                <Stack.Screen name="onboarding" options={{ headerShown: false, animation: 'fade' }} />
                <Stack.Screen name="login" options={{ headerShown: false }} />
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                <Stack.Screen name="settings" options={{ title: 'Settings', headerShown: true }} />
                <Stack.Screen name="expense/[id]" options={{ title: 'Expense detail', headerShown: true }} />
              </Stack>
            </AuthGate>
          </BottomSheetModalProvider>
        </AuthProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}
