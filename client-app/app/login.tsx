import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AnimatedLogo } from '@/components/AnimatedLogo';
import { Colors } from '@/constants/theme';
import { useAuth } from '@/lib/auth';
import { ApiError } from '@/lib/api';
import {
  enableBiometricLogin,
  getBiometricHardware,
  isBiometricLoginEnabled,
  unlockCredentialsWithBiometrics,
} from '@/lib/biometrics';

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [portalToken, setPortalToken] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [bioLoading, setBioLoading] = useState(false);
  const [bioReady, setBioReady] = useState(false);
  const [bioLabel, setBioLabel] = useState('Biometrics');

  useEffect(() => {
    (async () => {
      const hw = await getBiometricHardware();
      setBioLabel(hw.label);
      setBioReady(await isBiometricLoginEnabled());
    })();
  }, []);

  const maybeOfferBiometrics = useCallback(
    async (creds: {
      portal_token: string;
      phone?: string;
      email?: string;
      pin: string;
    }) => {
      const hw = await getBiometricHardware();
      if (!hw.compatible || !hw.enrolled) return;
      if (await isBiometricLoginEnabled()) return;
      Alert.alert(
        `Enable ${hw.label}?`,
        `Sign in next time with ${hw.label} only. Your portal number, contact, and PIN stay encrypted on this device.`,
        [
          { text: 'Not now', style: 'cancel' },
          {
            text: `Enable ${hw.label}`,
            onPress: async () => {
              try {
                await enableBiometricLogin(creds);
                setBioReady(true);
              } catch (err: any) {
                Alert.alert('Could not enable', err?.message || 'Try again from Profile.');
              }
            },
          },
        ],
      );
    },
    [],
  );

  async function onSubmit() {
    setError('');
    const portal = portalToken.trim();
    const id = identifier.trim();
    const pinValue = pin.trim();
    if (!portal || !id || !pinValue) {
      setError('Enter Client App Portal No., phone or email, and PIN.');
      return;
    }
    setLoading(true);
    try {
      const isEmail = id.includes('@');
      const creds = {
        portal_token: portal,
        pin: pinValue,
        ...(isEmail ? { email: id } : { phone: id }),
      };
      await signIn(creds);
      await maybeOfferBiometrics(creds);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Sign-in failed.');
    } finally {
      setLoading(false);
    }
  }

  async function onBiometricSignIn() {
    setError('');
    setBioLoading(true);
    try {
      const creds = await unlockCredentialsWithBiometrics();
      await signIn(creds);
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Biometric sign-in failed.');
    } finally {
      setBioLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.wrap}
      >
        <View style={styles.hero}>
          <AnimatedLogo size="medium" animated textColor={Colors.white} showTagline />
        </View>

        <View style={styles.formCard}>
          <Text style={styles.cardHeaderTitle}>Sign In to Wallet</Text>
          <Text style={styles.cardHeaderSub}>Secure access to policies, ID cards & documents</Text>

          {error ? (
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {bioReady ? (
            <Pressable
              style={({ pressed }) => [
                styles.bioButton,
                pressed && styles.buttonPressed,
                bioLoading && styles.buttonDisabled,
              ]}
              onPress={onBiometricSignIn}
              disabled={bioLoading || loading}
            >
              {bioLoading ? (
                <ActivityIndicator color={Colors.navy} />
              ) : (
                <Text style={styles.bioButtonText}>Unlock with {bioLabel}</Text>
              )}
            </Pressable>
          ) : null}

          {bioReady ? (
            <View style={styles.orRow}>
              <View style={styles.orLine} />
              <Text style={styles.orText}>or use PIN</Text>
              <View style={styles.orLine} />
            </View>
          ) : null}

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>CLIENT APP PORTAL NO.</Text>
            <TextInput
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="number-pad"
              value={portalToken}
              onChangeText={setPortalToken}
              placeholder="e.g. 482917"
              placeholderTextColor={Colors.mutedLight}
            />
          </View>

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

          <View style={styles.fieldGroup}>
            <Text style={styles.label}>ACCESS PIN</Text>
            <TextInput
              style={styles.input}
              secureTextEntry
              keyboardType="number-pad"
              textContentType="password"
              autoComplete="off"
              importantForAutofill="no"
              maxLength={8}
              value={pin}
              onChangeText={(value) => setPin(value.replace(/[^\d]/g, ''))}
              placeholder="4–8 digits"
              placeholderTextColor={Colors.mutedLight}
            />
          </View>

          <Pressable
            style={({ pressed }) => [
              styles.button,
              pressed && styles.buttonPressed,
              loading && styles.buttonDisabled,
            ]}
            onPress={onSubmit}
            disabled={loading || bioLoading}
          >
            {loading ? (
              <ActivityIndicator color={Colors.white} />
            ) : (
              <Text style={styles.buttonText}>Sign In</Text>
            )}
          </Pressable>

          <View style={styles.securityNoteContainer}>
            <Text style={styles.securityNoteText}>
              Encrypted on-device credentials · Token never stored in plain files
            </Text>
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
  bioButton: {
    backgroundColor: Colors.goldSoft,
    borderWidth: 1.5,
    borderColor: Colors.gold,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
    marginBottom: 4,
  },
  bioButtonText: { color: Colors.navy, fontWeight: '800', fontSize: 15 },
  orRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginVertical: 14,
  },
  orLine: { flex: 1, height: 1, backgroundColor: Colors.border },
  orText: { color: Colors.mutedLight, fontSize: 11, fontWeight: '700', letterSpacing: 0.4 },
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
  securityNoteText: { fontSize: 11, color: Colors.mutedLight, fontWeight: '500', textAlign: 'center' },
});
