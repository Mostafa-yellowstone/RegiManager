import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  StyleSheet,
  Text,
  View,
  type ImageStyle,
  type StyleProp,
} from 'react-native';

import { Colors } from '@/constants/theme';
import { downloadClientDocumentPreview } from '@/lib/openDocument';

type Props = {
  kind: string;
  id: number | string;
  title?: string;
  fileNameHint?: string | null;
  style?: StyleProp<ImageStyle>;
  resizeMode?: 'cover' | 'contain' | 'stretch';
};

/** Loads a server-rasterized PNG preview (works for PDF and image uploads). */
export function AuthDocumentImage({
  kind,
  id,
  title,
  style,
  resizeMode = 'cover',
}: Props) {
  const [uri, setUri] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    setUri(null);
    downloadClientDocumentPreview(kind, id, title || 'preview')
      .then((doc) => {
        if (cancelled) return;
        if (doc.isImage && doc.uri) setUri(doc.uri);
        else setFailed(true);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, id, title]);

  if (loading) {
    return (
      <View style={[styles.fallback, style as any]}>
        <ActivityIndicator color={Colors.gold} />
      </View>
    );
  }

  if (failed || !uri) {
    return (
      <View style={[styles.fallback, style as any]}>
        <Text style={styles.otherBadge}>DOC</Text>
        <Text style={styles.pdfSub}>Tap to open</Text>
      </View>
    );
  }

  return <Image source={{ uri }} style={style} resizeMode={resizeMode} />;
}

const styles = StyleSheet.create({
  fallback: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  otherBadge: {
    color: 'rgba(255,255,255,0.85)',
    fontWeight: '800',
    fontSize: 14,
    letterSpacing: 0.6,
  },
  pdfSub: {
    marginTop: 6,
    color: 'rgba(255,255,255,0.7)',
    fontSize: 11,
    fontWeight: '600',
  },
});
