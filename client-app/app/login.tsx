import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Colors } from '@/constants/theme';
import { useAuth } from '@/lib/auth';
import { ApiError } from '@/lib/api';

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [portalToken, setPortalToken] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function onSubmit() {
    setError('');
    const portal = portalToken.trim();
    const id = identifier.trim();
    const pinValue = pin.trim();
    if (!portal || !id || !pinValue) {
      setError('Enter portal code, phone or email, and PIN.');
      return;
    }
    setLoading(true);
    try {
      const isEmail = id.includes('@');
      await signIn({
        portal_token: portal,
        pin: pinValue,
        ...(isEmail ? { email: id } : { phone: id }),
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.wrap}
      >
        <View style={styles.hero}>
          <Text style={styles.brand}>RegiManager</Text>
          <Text style={styles.tagline}>Your insurance & DMV wallet</Text>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>Agency portal code</Text>
          <TextInput
            style={styles.input}
            autoCapitalize="none"
            autoCorrect={false}
            value={portalToken}
            onChangeText={setPortalToken}
            placeholder="From your agency"
            placeholderTextColor={Colors.muted}
          />

          <Text style={styles.label}>Phone or email</Text>
          <TextInput
            style={styles.input}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            value={identifier}
            onChangeText={setIdentifier}
            placeholder="5551234567 or you@email.com"
            placeholderTextColor={Colors.muted}
          />

          <Text style={styles.label}>PIN</Text>
          <TextInput
            style={styles.input}
            secureTextEntry={false}
            keyboardType="number-pad"
            textContentType="oneTimeCode"
            autoComplete="off"
            importantForAutofill="no"
            maxLength={8}
            value={pin}
            onChangeText={(value) => setPin(value.replace(/[^\d]/g, ''))}
            placeholder="4–8 digits"
            placeholderTextColor={Colors.muted}
          />

          {error ? <Text style={styles.error}>{error}</Text> : null}

          <Pressable style={styles.button} onPress={onSubmit} disabled={loading}>
            {loading ? (
              <ActivityIndicator color={Colors.white} />
            ) : (
              <Text style={styles.buttonText}>Sign in</Text>
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.navy },
  wrap: { flex: 1, justifyContent: 'center', padding: 24 },
  hero: { marginBottom: 28 },
  brand: {
    color: Colors.white,
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  tagline: { color: '#94A3B8', marginTop: 8, fontSize: 16 },
  form: {
    backgroundColor: Colors.white,
    borderRadius: 18,
    padding: 20,
    gap: 8,
  },
  label: { fontSize: 13, fontWeight: '700', color: Colors.muted, marginTop: 6 },
  input: {
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: Colors.text,
    backgroundColor: Colors.cream,
  },
  button: {
    marginTop: 14,
    backgroundColor: Colors.teal,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  buttonText: { color: Colors.white, fontWeight: '800', fontSize: 16 },
  error: { color: Colors.danger, marginTop: 8, fontWeight: '600' },
});
