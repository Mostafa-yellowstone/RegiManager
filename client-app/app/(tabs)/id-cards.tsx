import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { ApiError, fetchIdCards } from '@/lib/api';
import { openClientDocument } from '@/lib/openDocument';

const WIDTH = Dimensions.get('window').width;

export default function IdCardsScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchIdCards();
      setRows(data.results || []);
    } catch (err: any) {
      setError(err?.message || 'Could not load ID cards');
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

  async function openCard(doc: any) {
    setError('');
    setOpeningId(doc.id);
    try {
      await openClientDocument('insurance', doc.id, doc.title || 'ID Card');
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Could not open ID card');
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
      horizontal
      pagingEnabled
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}
      showsHorizontalScrollIndicator={false}
    >
      {error ? (
        <View style={[styles.card, { width: WIDTH - 40 }]}>
          <Text style={styles.error}>{error}</Text>
        </View>
      ) : null}
      {!rows.length && !error ? (
        <View style={[styles.card, { width: WIDTH - 40 }]}>
          <Text style={styles.empty}>No insurance ID cards uploaded yet.</Text>
        </View>
      ) : null}
      {rows.map((doc) => (
        <Pressable
          key={doc.id}
          style={[styles.card, { width: WIDTH - 40 }]}
          onPress={() => openCard(doc)}
          disabled={openingId != null}
        >
          <Text style={styles.badge}>ID CARD</Text>
          <Text style={styles.title}>{doc.title || doc.document_type_display}</Text>
          <Text style={styles.meta}>Policy {doc.policy_number || '—'}</Text>
          {openingId === doc.id ? (
            <ActivityIndicator color={Colors.teal} style={{ marginTop: 24 }} />
          ) : (
            <Text style={styles.hint}>Tap to open file</Text>
          )}
        </Pressable>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { paddingVertical: 24, paddingHorizontal: 20, alignItems: 'center' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  card: {
    backgroundColor: Colors.navy,
    borderRadius: 20,
    padding: 24,
    marginRight: 14,
    minHeight: 220,
    justifyContent: 'center',
  },
  badge: {
    color: Colors.tealSoft,
    fontWeight: '800',
    letterSpacing: 1.2,
    fontSize: 12,
    marginBottom: 12,
  },
  title: { color: Colors.white, fontSize: 22, fontWeight: '800' },
  meta: { color: '#94A3B8', marginTop: 10 },
  hint: { color: Colors.teal, marginTop: 24, fontWeight: '700' },
  empty: { color: '#CBD5E1', textAlign: 'center' },
  error: { color: '#FCA5A5' },
});
