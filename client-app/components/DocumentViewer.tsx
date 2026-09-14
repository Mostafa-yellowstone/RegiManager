import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Dimensions,
  Image,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';

import { Colors, Radius } from '@/constants/theme';
import {
  downloadClientDocument,
  shareDownloadedDocument,
  type DownloadedDocument,
} from '@/lib/openDocument';

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get('window');

type Props = {
  visible: boolean;
  kind: string;
  id: number | string;
  title?: string;
  fileNameHint?: string | null;
  variant?: 'id_card' | 'document';
  onClose: () => void;
};

function pdfHtml(base64: string): string {
  // data: PDF embed works best on iOS; Android may still fall back to share.
  return `<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=3" />
  <style>
    html, body { margin:0; padding:0; height:100%; background:#0B192C; }
    .wrap { display:flex; height:100%; align-items:stretch; justify-content:center; }
    embed, iframe, object { width:100%; height:100%; border:0; }
  </style>
</head>
<body>
  <div class="wrap">
    <embed src="data:application/pdf;base64,${base64}" type="application/pdf" />
  </div>
</body>
</html>`;
}

export function DocumentViewerModal({
  visible,
  kind,
  id,
  title = 'Document',
  fileNameHint,
  variant = 'document',
  onClose,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [file, setFile] = useState<DownloadedDocument | null>(null);
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    if (!visible || !id) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    setFile(null);
    downloadClientDocument(kind, id, title, { fileNameHint })
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
  }, [visible, kind, id, title, fileNameHint]);

  const isIdCard = variant === 'id_card';
  const pdfSource = useMemo(() => {
    if (!file?.isPdf || !file.base64) return null;
    return { html: pdfHtml(file.base64), baseUrl: '' };
  }, [file]);

  async function onOpenExternally() {
    if (!file) return;
    setSharing(true);
    try {
      await shareDownloadedDocument(file);
    } catch (err: any) {
      setError(err?.message || 'Could not open externally');
    } finally {
      setSharing(false);
    }
  }

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
              {file?.ext ? (
                <Text style={[styles.extChip, !isIdCard && styles.extChipDoc]}>
                  .{file.ext.toUpperCase()}
                  {file.isPdf ? ' · PDF' : file.isImage ? ' · IMAGE' : ''}
                </Text>
              ) : null}
            </View>
            <Pressable style={[styles.closeBtn, !isIdCard && styles.closeBtnDoc]} onPress={onClose}>
              <Text style={[styles.closeText, !isIdCard && styles.closeTextDoc]}>Close</Text>
            </Pressable>
          </View>

          <View style={styles.body}>
            {loading ? (
              <View style={styles.center}>
                <ActivityIndicator color={Colors.gold} size="large" />
                <Text style={styles.hint}>Loading secure preview…</Text>
              </View>
            ) : error ? (
              <View style={styles.center}>
                <Text style={styles.error}>{error}</Text>
                <Pressable style={styles.secondaryBtn} onPress={onOpenExternally} disabled={!file || sharing}>
                  <Text style={styles.secondaryBtnText}>
                    {sharing ? 'Opening…' : 'Open with device app'}
                  </Text>
                </Pressable>
              </View>
            ) : file?.isImage ? (
              <View style={[styles.imageFrame, isIdCard && styles.imageFrameId]}>
                {isIdCard ? (
                  <View style={styles.idChrome}>
                    <View style={styles.idChromeTop}>
                      <Text style={styles.idChromeSeal}>◆</Text>
                      <Text style={styles.idChromeLabel}>REGIMANAGER WALLET</Text>
                    </View>
                    <Image source={{ uri: file.uri }} style={styles.idImage} resizeMode="contain" />
                    <Text style={styles.idChromeFoot}>{title}</Text>
                  </View>
                ) : (
                  <Image source={{ uri: file.uri }} style={styles.image} resizeMode="contain" />
                )}
              </View>
            ) : file?.isPdf && pdfSource ? (
              <View style={{ flex: 1 }}>
                <WebView
                  originWhitelist={['*']}
                  source={pdfSource}
                  style={styles.webview}
                  allowFileAccess
                  allowUniversalAccessFromFileURLs
                  mixedContentMode="always"
                  startInLoadingState
                  renderLoading={() => (
                    <View style={styles.center}>
                      <ActivityIndicator color={Colors.gold} />
                    </View>
                  )}
                />
                {Platform.OS === 'android' ? (
                  <View style={styles.androidPdfBar}>
                    <Text style={styles.androidPdfHint}>
                      For the sharpest PDF view on Android, open with your device viewer.
                    </Text>
                    <Pressable style={styles.secondaryBtn} onPress={onOpenExternally} disabled={sharing}>
                      <Text style={styles.secondaryBtnText}>
                        {sharing ? 'Opening…' : 'Open PDF externally'}
                      </Text>
                    </Pressable>
                  </View>
                ) : null}
              </View>
            ) : (
              <View style={styles.center}>
                <Text style={styles.hint}>
                  In-app preview isn’t available for .{file?.ext || 'this'} files.
                </Text>
                <Pressable style={styles.secondaryBtn} onPress={onOpenExternally} disabled={sharing}>
                  <Text style={styles.secondaryBtnText}>
                    {sharing ? 'Opening…' : 'Open with device app'}
                  </Text>
                </Pressable>
              </View>
            )}
          </View>

          {file && !loading ? (
            <View style={[styles.footer, !isIdCard && styles.footerDoc]}>
              <Pressable style={styles.footerBtn} onPress={onOpenExternally} disabled={sharing}>
                <Text style={styles.footerBtnText}>{sharing ? 'Opening…' : 'Share / Open externally'}</Text>
              </Pressable>
            </View>
          ) : null}
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
    maxHeight: SCREEN_H * 0.92,
    minHeight: SCREEN_H * 0.58,
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
  extChip: {
    marginTop: 4,
    fontSize: 10,
    fontWeight: '700',
    color: 'rgba(255,255,255,0.55)',
    letterSpacing: 0.4,
  },
  extChipDoc: { color: Colors.mutedLight },
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
  error: { color: '#FCA5A5', fontWeight: '700', textAlign: 'center', marginBottom: 12 },
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
    shadowColor: '#C9A227',
    shadowOpacity: 0.25,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
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
  webview: { flex: 1, backgroundColor: '#0B192C' },
  androidPdfBar: {
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(148,163,184,0.25)',
    gap: 8,
  },
  androidPdfHint: {
    color: Colors.mutedLight,
    fontSize: 12,
    textAlign: 'center',
    fontWeight: '500',
  },
  secondaryBtn: {
    marginTop: 8,
    backgroundColor: Colors.gold,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: Radius.md,
  },
  secondaryBtnText: { color: Colors.navy, fontWeight: '800', fontSize: 13, textAlign: 'center' },
  footer: {
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: 'rgba(148,163,184,0.25)',
  },
  footerDoc: { backgroundColor: Colors.white, borderTopColor: Colors.border },
  footerBtn: {
    alignItems: 'center',
    paddingVertical: 12,
    borderRadius: Radius.md,
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  footerBtnText: { color: Colors.gold, fontWeight: '800', fontSize: 13 },
});
