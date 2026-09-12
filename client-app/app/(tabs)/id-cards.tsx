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
      await openClientDocument(doc.kind || 'insurance', doc.id, doc.title || 'ID Card');
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Could not open ID card');
    } finally {
      setOpeningId(null);
    }
  }

  if (loading && !rows.length) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={loading}
          onRefresh={load}
          tintColor={Colors.primaryMid}
        />
      }
    >
      {/* Intro Header */}
      <View style={styles.headerBox}>
        <Text style={styles.headerTitle}>Digital Insurance Cards</Text>
        <Text style={styles.headerSubtitle}>
          Swipe horizontally to view all registered policy identity cards
        </Text>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      {!rows.length && !error ? (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyIcon}>🎴</Text>
          <Text style={styles.emptyTitle}>No Digital ID Cards</Text>
          <Text style={styles.emptyText}>No insurance ID cards have been issued to your wallet yet.</Text>
        </View>
      ) : null}

      {rows.length > 0 ? (
        <ScrollView
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.carouselContainer}
        >
          {rows.map((doc, index) => (
            <Pressable
              key={doc.id}
              style={({ pressed }) => [
                styles.idCard,
                { width: WIDTH - 40 },
                pressed && styles.pressedCard,
              ]}
              onPress={() => openCard(doc)}
              disabled={openingId != null}
            >
              {/* Top Security Line */}
              <View style={styles.cardTopBar}>
                <View style={styles.chipGraphic}>
                  <View style={styles.chipLine} />
                  <View style={styles.chipLine} />
                </View>
                <View style={styles.securityBadge}>
                  <Text style={styles.securityBadgeText}>VERIFIED ID</Text>
                </View>
              </View>

              {/* Title & Metadata */}
              <View style={styles.cardMain}>
                <Text style={styles.cardTypeLabel}>INSURANCE IDENTIFICATION</Text>
                <Text style={styles.cardTitle}>{doc.title || doc.document_type_display}</Text>
                <Text style={styles.policyNumberText}>
                  POLICY #{doc.policy_number || 'UNKNOWN'}
                </Text>
              </View>

              <View style={styles.cardDivider} />

              {/* Card Footer Callout */}
              <View style={styles.cardFooter}>
                <View style={styles.cardCounter}>
                  <Text style={styles.counterText}>{index + 1} of {rows.length}</Text>
                </View>
                {openingId === doc.id ? (
                  <ActivityIndicator color={Colors.white} size="small" />
                ) : (
                  <View style={styles.actionBtn}>
                    <Text style={styles.actionBtnText}>Tap to Open Document 📄</Text>
                  </View>
                )}
              </View>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}

      {rows.length > 1 ? (
        <Text style={styles.swipeHint}>‹ Swipe for next card ›</Text>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: Colors.cream },
  content: { paddingVertical: 18, paddingHorizontal: 0, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  headerBox: { paddingHorizontal: 20, marginBottom: 16 },
  headerTitle: { fontSize: 22, fontWeight: '800', color: Colors.navy, letterSpacing: -0.3 },
  headerSubtitle: { color: Colors.muted, fontSize: 13, fontWeight: '500', marginTop: 2 },
  errorBox: {
    marginHorizontal: 20,
    backgroundColor: Colors.dangerLight,
    borderWidth: 1,
    borderColor: '#FCA5A5',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  errorText: { color: Colors.danger, fontSize: 13, fontWeight: '600' },
  emptyCard: {
    marginHorizontal: 20,
    backgroundColor: Colors.white,
    borderRadius: 20,
    padding: 32,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: Colors.border,
  },
  emptyIcon: { fontSize: 44, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: Colors.navy },
  emptyText: { color: Colors.muted, fontSize: 13, textAlign: 'center', marginTop: 4 },
  carouselContainer: { paddingHorizontal: 20, gap: 16 },
  idCard: {
    backgroundColor: Colors.navy,
    borderRadius: 22,
    padding: 24,
    minHeight: 230,
    justifyContent: 'space-between',
    borderWidth: 1.5,
    borderColor: 'rgba(255, 255, 255, 0.15)',
    shadowColor: Colors.navy,
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.25,
    shadowRadius: 18,
    elevation: 6,
  },
  pressedCard: { opacity: 0.95, transform: [{ scale: 0.99 }] },
  cardTopBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  chipGraphic: {
    width: 38,
    height: 28,
    borderRadius: 6,
    backgroundColor: '#D97706',
    padding: 4,
    justifyContent: 'space-around',
    borderWidth: 1,
    borderColor: '#FBBF24',
  },
  chipLine: { height: 2, backgroundColor: 'rgba(255, 255, 255, 0.6)', borderRadius: 1 },
  securityBadge: {
    backgroundColor: 'rgba(59, 130, 246, 0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(59, 130, 246, 0.4)',
  },
  securityBadgeText: { color: '#93C5FD', fontSize: 10, fontWeight: '800', letterSpacing: 0.8 },
  cardMain: { marginTop: 16 },
  cardTypeLabel: { color: '#94A3B8', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  cardTitle: { color: Colors.white, fontSize: 22, fontWeight: '800', marginTop: 4, letterSpacing: -0.4 },
  policyNumberText: { color: '#CBD5E1', fontSize: 14, fontWeight: '700', marginTop: 6, letterSpacing: 0.5 },
  cardDivider: { height: 1, backgroundColor: 'rgba(255, 255, 255, 0.12)', marginVertical: 14 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardCounter: { backgroundColor: 'rgba(255, 255, 255, 0.1)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  counterText: { color: '#94A3B8', fontSize: 11, fontWeight: '700' },
  actionBtn: {
    backgroundColor: Colors.primaryMid,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 10,
  },
  actionBtnText: { color: Colors.white, fontWeight: '800', fontSize: 12 },
  swipeHint: { textAlign: 'center', color: Colors.muted, fontSize: 12, fontWeight: '600', marginTop: 16 },
});
