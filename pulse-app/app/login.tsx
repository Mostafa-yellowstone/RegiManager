import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Redirect } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PulseLogo } from '@/components/PulseLogo';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { hapticMedium, hapticSuccess } from '@/lib/haptics';
import { Colors } from '@/lib/theme';

export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { token, login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  if (token) return <Redirect href="/(tabs)" />;

  async function onSubmit() {
    setError('');
    setLoading(true);
    await hapticMedium();
    try {
      await login(username, password);
      await hapticSuccess();
    } catch (err: any) {
      const raw = err instanceof ApiError ? err.message : err?.message || 'Login failed';
      if (typeof raw === 'string' && /invalid credentials/i.test(raw)) {
        setError(
          'Invalid credentials. Use your web CRM staff username/password (owner account), not the client Wallet login.',
        );
      } else {
        setError(raw);
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: Colors.navy }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <LinearGradient colors={['#0F3D4C', '#0B2E3A', '#083344']} style={{ flex: 1 }}>
        <ScrollView
          contentContainerStyle={{
            flexGrow: 1,
            justifyContent: 'center',
            paddingHorizontal: 24,
            paddingTop: insets.top + 24,
            paddingBottom: insets.bottom + 28,
          }}
          keyboardShouldPersistTaps="handled"
        >
          <View style={{ alignItems: 'center', marginBottom: 28 }}>
            <PulseLogo size="large" showText showTagline animated />
          </View>

          <Text style={{ color: 'rgba(255,255,255,0.7)', fontSize: 15, lineHeight: 22, textAlign: 'center' }}>
            Owner access only. Sign in with your RegiManager organization owner account (same username and
            password as the web CRM).
          </Text>

          <View style={{ marginTop: 28, gap: 12 }}>
            <TextInput
              className="rounded-xl border border-white/20 bg-white/10 px-4 py-3.5 text-body text-white"
              placeholder="Username or email"
              placeholderTextColor="rgba(255,255,255,0.45)"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              textContentType="username"
              value={username}
              onChangeText={setUsername}
            />
            <TextInput
              className="rounded-xl border border-white/20 bg-white/10 px-4 py-3.5 text-body text-white"
              placeholder="Password"
              placeholderTextColor="rgba(255,255,255,0.45)"
              secureTextEntry
              textContentType="password"
              value={password}
              onChangeText={setPassword}
            />
            {error ? (
              <Text className="text-caption font-semibold text-red-300">{error}</Text>
            ) : null}
            <Pressable
              onPress={onSubmit}
              disabled={loading || !username || !password}
              className="mt-1 items-center rounded-xl bg-gold py-3.5"
              android_ripple={{ color: 'rgba(0,0,0,0.12)' }}
              style={{ opacity: loading || !username || !password ? 0.6 : 1 }}
            >
              {loading ? (
                <ActivityIndicator color="#1A2B48" />
              ) : (
                <Text className="text-body font-extrabold text-navy">Sign in</Text>
              )}
            </Pressable>
          </View>
        </ScrollView>
      </LinearGradient>
    </KeyboardAvoidingView>
  );
}
