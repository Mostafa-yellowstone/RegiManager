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
        {/* Header Header & Branding */}
        <View style={styles.hero}>
          <View style={styles.badgeContainer}>
            <View style={styles.badgeDot} />
            <Text style={styles.badgeText}>CLIENT PORTAL</Text>
          </View>
          <Text style={styles.brand}>RegiManager</Text>
          <Text style={styles.tagline}>Insurance & DMV Mobile Wallet</Text>
        </View>

        {/* Input Card Container */}
        <View style={styles.formCard}>
          <Text style={styles.cardHeaderTitle}>Sign In to Wallet</Text>
          <Text style={styles.cardHeaderSub}>Access policies, ID cards & receipts</Text>

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {/* Agency Portal Token */}
          <View style={styles.fieldGroup}>
            <Text style={styles.label}>AGENCY PORTAL CODE</Text>
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              value={portalToken}
              onChangeText={setPortalToken}
              placeholder="e.g. PORTAL123"
              placeholderTextColor={Colors.mutedLight}
            />
          </View>

          {/* Identifier (Phone or Email) */}
          <View style={styles.fieldGroup}>
            <Text style={styles.label}>PHONE OR EMAIL</Text>
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              value={identifier}
              onChangeText={setIdentifier}
              placeholder="5551234567 or client@agency.com"
              placeholderTextColor={Colors.mutedLight}
            />
          </View>

          {/* PIN */}
          <View style={styles.fieldGroup}>
            <Text style={styles.label}>ACCESS PIN</Text>
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
              placeholderTextColor={Colors.mutedLight}
            />
          </View>

          {/* Sign In Button */}
          <Pressable
            style={({ pressed }) => [
              styles.button,
              pressed && styles.buttonPressed,
              loading && styles.buttonDisabled,
            ]}
            onPress={onSubmit}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color={Colors.white} />
            ) : (
              <Text style={styles.buttonText}>Sign In</Text>
            )}
          </Pressable>

          <View style={styles.securityNoteContainer}>
            <Text style={styles.securityNoteText}>🔒 256-bit Encrypted Government Connection</Text>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: Colors.navy },
  wrap: { flex: 1, justifyContent: 'center', paddingHorizontal: 22, paddingVertical: 12 },
  hero: { marginBottom: 24, alignItems: 'center' },
  badgeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(59, 130, 246, 0.15)',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(59, 130, 246, 0.3)',
    marginBottom: 12,
  },
  badgeDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#60A5FA',
    marginRight: 6,
  },
  badgeText: {
    color: '#93C5FD',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.2,
  },
  brand: {
    color: Colors.white,
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -0.6,
    textAlign: 'center',
  },
  tagline: { color: '#94A3B8', marginTop: 6, fontSize: 15, fontWeight: '500', textAlign: 'center' },
  formCard: {
    backgroundColor: Colors.white,
    borderRadius: 24,
    padding: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.2,
    shadowRadius: 20,
    elevation: 8,
  },
  cardHeaderTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: Colors.navy,
    letterSpacing: -0.3,
  },
  cardHeaderSub: {
    fontSize: 13,
    color: Colors.muted,
    marginTop: 2,
    marginBottom: 20,
  },
  errorBox: {
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  fieldGroup: { marginBottom: 16 },
  label: { fontSize: 11, fontWeight: '800', color: Colors.muted, marginBottom: 6, letterSpacing: 0.6 },
  input: {
    borderWidth: 1.5,
    borderColor: Colors.border,
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 13,
    fontSize: 15,
    fontWeight: '600',
    color: Colors.text,
    backgroundColor: '#F8FAFC',
  },
  button: {
    marginTop: 8,
    backgroundColor: Colors.primaryMid,
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
    shadowColor: Colors.primaryMid,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 4,
  },
  buttonPressed: { opacity: 0.88, transform: [{ scale: 0.99 }] },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: Colors.white, fontWeight: '800', fontSize: 16, letterSpacing: 0.2 },
  securityNoteContainer: { marginTop: 18, alignItems: 'center' },
  securityNoteText: { fontSize: 12, color: Colors.mutedLight, fontWeight: '500' },
});
