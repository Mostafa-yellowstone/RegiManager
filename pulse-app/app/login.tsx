import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Redirect } from 'expo-router';

import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { hapticMedium, hapticSuccess } from '@/lib/haptics';

export default function LoginScreen() {
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
      className="flex-1 bg-navy"
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View className="flex-1 justify-center px-6">
        <Text className="text-caption font-bold uppercase tracking-widest text-gold">
          RegiManager
        </Text>
        <Text className="mt-2 text-display text-white">Pulse</Text>
        <Text className="mt-2 text-body text-white/70">
          Owner tracking — sign in with your RegiManager dashboard staff account
          (same username/password as the web CRM). Not the client Wallet PIN.
        </Text>

        <View className="mt-10 gap-3">
          <TextInput
            className="rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-body text-white"
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
            className="rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-body text-white"
            placeholder="Password"
            placeholderTextColor="rgba(255,255,255,0.45)"
            secureTextEntry
            textContentType="password"
            value={password}
            onChangeText={setPassword}
          />
          {error ? <Text className="text-caption font-semibold text-red-300">{error}</Text> : null}
          <Pressable
            onPress={onSubmit}
            disabled={loading || !username || !password}
            className="mt-2 items-center rounded-xl bg-gold py-3.5"
            android_ripple={{ color: 'rgba(0,0,0,0.12)' }}
          >
            {loading ? (
              <ActivityIndicator color="#1A2B48" />
            ) : (
              <Text className="text-body font-extrabold text-navy">Sign in</Text>
            )}
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
