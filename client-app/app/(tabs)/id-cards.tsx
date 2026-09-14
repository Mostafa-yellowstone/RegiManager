import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';

import { AuthDocumentImage } from '@/components/AuthDocumentImage';
import { DocumentViewerModal } from '@/components/DocumentViewer';
import { Colors } from '@/constants/theme';
import { fetchIdCards } from '@/lib/api';

const WIDTH = Dimensions.get('window').width;
const CARD_W = WIDTH - 48;

type ViewerTarget = {
  kind: string;
  id: number | string;
  title: string;
  fileNameHint?: string | null;
} | null;

export default function IdCardsScreen() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [viewer, setViewer] = useState<ViewerTarget>(null);

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

  function openCard(doc: any) {
    setViewer({
      kind: doc.kind || 'insurance',
      id: doc.id,
      title: doc.title || doc.document_type_display || 'ID Card',
      fileNameHint: doc.file_name || null,
    });
  }

  function onScroll(e: NativeSyntheticEvent<NativeScrollEvent>) {
    const x = e.nativeEvent.contentOffset.x;
    setPage(Math.round(x / (CARD_W + 14)));
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
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={Colors.primaryMid} />}
    >
      <Text style={styles.h1}>Identity Cards</Text>
      <Text style={styles.sub}>Insurance ID cards and driver licenses · swipe pager</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {!rows.length ? (
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>No cards uploaded yet</Text>
          <Text style={styles.sub}>
            Ask your agency to upload insurance ID cards or driver license scans on your profile.
          </Text>
        </View>
      ) : (
        <>
          <ScrollView
            horizontal
            pagingEnabled={false}
            decelerationRate="fast"
            snapToInterval={CARD_W + 14}
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: 16 }}
            onScroll={onScroll}
            scrollEventThrottle={16}
          >
            {rows.map((doc, index) => {
              const isDl = doc.document_type === 'driver_license';
              const key = `${doc.kind}-${doc.id}`;
              return (
                <Pressable
                  key={key}
                  style={[styles.card, { width: CARD_W, backgroundColor: isDl ? '#0F766E' : Colors.navy }]}
                  onPress={() => openCard(doc)}
                >
                  <View style={styles.cardTop}>
                    <Text style={styles.cardKind}>{isDl ? 'DRIVER LICENSE' : 'INSURANCE ID'}</Text>
                    <Text style={styles.cardCount}>
                      {index + 1}/{rows.length}
                    </Text>
                  </View>
                  <View style={styles.previewWrap}>
                    <AuthDocumentImage
                      kind={doc.kind || 'insurance'}
                      id={doc.id}
                      title={doc.title || 'ID Card'}
                      fileNameHint={doc.file_name || null}
                      style={styles.previewImage}
                    />
                  </View>
                  <View style={styles.formatRow}>
                    <Text style={styles.formatChip}>
                      {(doc.file_ext || 'FILE').toString().toUpperCase()}
                    </Text>
                    <Text style={styles.cardMetaInline}>
                      {doc.policy_number
                        ? `Policy #${doc.policy_number}`
                        : doc.vehicle_label || 'Official document'}
                    </Text>
                  </View>
                  <Text style={styles.cardTitle} numberOfLines={2}>
                    {doc.title || doc.document_type_display}
                  </Text>
                  <View style={styles.cardFooter}>
                    <Text style={styles.open}>Tap to view</Text>
                  </View>
                </Pressable>
              );
            })}
          </ScrollView>
          <View style={styles.dots}>
            {rows.map((_, i) => (
              <View key={i} style={[styles.dot, i === page && styles.dotOn]} />
            ))}
          </View>
        </>
      )}

      {viewer ? (
        <DocumentViewerModal
          visible
          kind={viewer.kind}
          id={viewer.id}
          title={viewer.title}
          fileNameHint={viewer.fileNameHint}
          variant="id_card"
          onClose={() => setViewer(null)}
        />
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F1F5F9' },
  content: { paddingVertical: 16, paddingBottom: 40 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  h1: { fontSize: 22, fontWeight: '800', color: Colors.navy, paddingHorizontal: 16 },
  sub: { color: Colors.muted, marginTop: 4, marginBottom: 16, paddingHorizontal: 16, fontSize: 13 },
  error: { color: Colors.danger, paddingHorizontal: 16, marginBottom: 10, fontWeight: '600' },
  empty: {
    marginHorizontal: 16, backgroundColor: '#fff', borderRadius: 16, padding: 20,
    borderWidth: 1, borderColor: Colors.border,
  },
  emptyTitle: { fontWeight: '800', color: Colors.navy, fontSize: 16, marginBottom: 6 },
  card: {
    borderRadius: 22,
    padding: 16,
    marginRight: 14,
    minHeight: 320,
    justifyContent: 'space-between',
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between' },
  cardKind: { color: 'rgba(255,255,255,0.7)', fontWeight: '800', fontSize: 11, letterSpacing: 1 },
  cardCount: { color: 'rgba(255,255,255,0.7)', fontWeight: '700', fontSize: 12 },
  previewWrap: {
    marginTop: 12,
    borderRadius: 14,
    overflow: 'hidden',
    backgroundColor: 'rgba(255,255,255,0.12)',
    height: 140,
  },
  previewImage: { width: '100%', height: '100%' },
  formatRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 12,
  },
  formatChip: {
    color: Colors.gold,
    fontWeight: '900',
    fontSize: 10,
    letterSpacing: 0.8,
    backgroundColor: 'rgba(201,162,39,0.18)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    overflow: 'hidden',
  },
  cardTitle: { color: '#fff', fontSize: 18, fontWeight: '800', marginTop: 10 },
  cardMeta: { color: 'rgba(255,255,255,0.8)', marginTop: 6, fontWeight: '600' },
  cardMetaInline: { color: 'rgba(255,255,255,0.75)', fontWeight: '600', fontSize: 12, flex: 1 },
  cardFooter: { marginTop: 14 },
  open: { color: '#fff', fontWeight: '800' },
  dots: { flexDirection: 'row', justifyContent: 'center', gap: 6, marginTop: 14 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#CBD5E1' },
  dotOn: { backgroundColor: Colors.navy, width: 18 },
});
