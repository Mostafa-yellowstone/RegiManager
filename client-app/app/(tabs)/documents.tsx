import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { ApiError, fetchDocuments } from '@/lib/api';
import { openClientDocument } from '@/lib/openDocument';

export default function DocumentsScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchDocuments();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load documents');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      setLoading(true);
      load();
    }, [load]),
  );

  async function onOpen(doc: any) {
    const key = `${doc.kind}-${doc.id}`;
    setError('');
    setOpeningId(key);
    try {
      await openClientDocument(doc.kind, doc.id, doc.title || doc.document_type_display);
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Could not open file');
    } finally {
      setOpeningId(null);
    }
  }

  if (loading && !rows.length) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.teal} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {!rows.length ? <Text style={styles.empty}>No wallet documents yet.</Text> : null}
      {rows.map((doc) => {
        const key = `${doc.kind}-${doc.id}`;
        const busy = openingId === key;
        return (
          <Pressable key={key} style={styles.row} onPress={() => onOpen(doc)} disabled={!!openingId}>
            <View style={{ flex: 1 }}>
              <Text style={styles.kind}>{doc.kind === 'dmv' ? 'DMV' : 'Insurance'}</Text>
              <Text style={styles.title}>{doc.title || doc.document_type_display}</Text>
              <Text style={styles.meta}>
                {doc.document_type_display}
                {doc.policy_number ? ` · ${doc.policy_number}` : ''}
              </Text>
            </View>
            {busy ? (
              <ActivityIndicator color={Colors.teal} />
            ) : (
              <Text style={styles.open}>Open</Text>
            )}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  error: { color: Colors.danger, marginBottom: 12 },
  empty: { color: Colors.muted, textAlign: 'center', marginTop: 40 },
  row: {
    backgroundColor: Colors.white,
    borderRadius: 14,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: Colors.border,
    flexDirection: 'row',
    alignItems: 'center',
  },
  kind: {
    fontSize: 11,
    fontWeight: '800',
    color: Colors.teal,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  title: { fontWeight: '800', color: Colors.navy, marginTop: 4, fontSize: 16 },
  meta: { color: Colors.muted, marginTop: 4 },
  open: { color: Colors.teal, fontWeight: '800', marginLeft: 12 },
});
