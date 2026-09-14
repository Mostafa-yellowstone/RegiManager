import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';

import { Colors, Radius } from '@/constants/theme';
import { downloadClientDocument, type DownloadedDocument } from '@/lib/openDocument';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

type Props = {
  visible: boolean;
  kind: string;
  id: number | string;
  title?: string;
  /** Visual chrome: id_card | document */
  variant?: 'id_card' | 'document';
  onClose: () => void;
};

export function DocumentViewerModal({
  visible,
  kind,
  id,
  title = 'Document',
  variant = 'document',
  onClose,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [file, setFile] = useState<DownloadedDocument | null>(null);

  useEffect(() => {
    if (!visible || !id) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    setFile(null);
    downloadClientDocument(kind, id, title)
      .then((doc) => {
        if (!cancelled) setFile(doc);
      })
      .catch((err: any) => {
        if (!cancelled) setError(err?.message || 'Could not load document');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, kind, id, title]);

  const isIdCard = variant === 'id_card';

  return (
    <Modal visible={visible} animationType="fade" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.sheet, isIdCard && styles.sheetId]}>
          <View style={[styles.head, !isIdCard && styles.headDoc]}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.eyebrow, !isIdCard && styles.eyebrowDoc]}>
                {isIdCard ? 'DIGITAL ID' : 'DOCUMENT PREVIEW'}
              </Text>
              <Text style={[styles.headTitle, !isIdCard && styles.headTitleDoc]} numberOfLines={1}>
                {title}
              </Text>
            </View>
            <Pressable style={[styles.closeBtn, !isIdCard && styles.closeBtnDoc]} onPress={onClose}>
              <Text style={[styles.closeText, !isIdCard && styles.closeTextDoc]}>Close</Text>
            </Pressable>
          </View>

          <View style={styles.body}>
            {loading ? (
              <View style={styles.center}>
                <ActivityIndicator color={Colors.gold} size="large" />
                <Text style={styles.hint}>Loading preview…</Text>
              </View>
            ) : error ? (
              <View style={styles.center}>
                <Text style={styles.error}>{error}</Text>
              </View>
            ) : file?.isImage ? (
              <View style={[styles.imageFrame, isIdCard && styles.imageFrameId]}>
                {isIdCard ? (
                  <View style={styles.idChrome}>
                    <View style={styles.idChromeTop}>
                      <Text style={styles.idChromeSeal}>◆</Text>
                      <Text style={styles.idChromeLabel}>REGIMANAGER WALLET</Text>
                    </View>
                    <Image
                      source={{ uri: file.uri }}
                      style={styles.idImage}
                      resizeMode="contain"
                    />
                    <Text style={styles.idChromeFoot}>{title}</Text>
                  </View>
                ) : (
                  <Image source={{ uri: file.uri }} style={styles.image} resizeMode="contain" />
                )}
              </View>
            ) : file?.isPdf ? (
              <WebView
                source={{ uri: file.uri }}
                style={styles.webview}
                originWhitelist={['*']}
                allowFileAccess
                allowUniversalAccessFromFileURLs
                startInLoadingState
                renderLoading={() => (
                  <View style={styles.center}>
                    <ActivityIndicator color={Colors.gold} />
                  </View>
                )}
              />
            ) : (
              <View style={styles.center}>
                <Text style={styles.hint}>Preview not available for this file type.</Text>
              </View>
            )}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.72)',
    justifyContent: 'center',
    padding: 16,
  },
  sheet: {
    backgroundColor: Colors.cream,
    borderRadius: Radius.xl,
    maxHeight: SCREEN_H * 0.9,
    minHeight: SCREEN_H * 0.55,
    overflow: 'hidden',
  },
  sheetId: {
    backgroundColor: '#0B192C',
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(148,163,184,0.25)',
  },
  headDoc: {
    backgroundColor: Colors.white,
    borderBottomColor: Colors.border,
  },
  eyebrow: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
    color: Colors.gold,
  },
  eyebrowDoc: { color: Colors.muted },
  headTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: Colors.white,
    marginTop: 2,
  },
  headTitleDoc: { color: Colors.navy },
  closeBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: Radius.md,
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  closeBtnDoc: { backgroundColor: Colors.primarySubtle },
  closeText: { color: Colors.white, fontWeight: '800', fontSize: 12 },
  closeTextDoc: { color: Colors.navy },
  body: { flex: 1, minHeight: 320 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 },
  hint: { color: Colors.mutedLight, marginTop: 10, fontSize: 13, textAlign: 'center' },
  error: { color: '#FCA5A5', fontWeight: '700', textAlign: 'center' },
  imageFrame: {
    flex: 1,
    padding: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageFrameId: { padding: 16 },
  image: {
    width: SCREEN_W - 56,
    height: SCREEN_H * 0.55,
  },
  idChrome: {
    width: '100%',
    backgroundColor: '#132337',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: 'rgba(201,162,39,0.45)',
    padding: 14,
    ...({
      shadowColor: '#C9A227',
      shadowOpacity: 0.25,
      shadowRadius: 18,
      shadowOffset: { width: 0, height: 8 },
      elevation: 8,
    } as const),
  },
  idChromeTop: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  idChromeSeal: { color: Colors.gold, fontSize: 14, fontWeight: '800' },
  idChromeLabel: {
    color: Colors.gold,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1,
  },
  idImage: {
    width: '100%',
    height: Math.min(SCREEN_H * 0.48, 420),
    borderRadius: 12,
    backgroundColor: '#0B192C',
  },
  idChromeFoot: {
    marginTop: 12,
    color: 'rgba(255,255,255,0.7)',
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
  webview: { flex: 1, backgroundColor: Colors.cream },
});
