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
import { downloadClientDocument } from '@/lib/openDocument';

type Props = {
  kind: string;
  id: number | string;
  title?: string;
  fileNameHint?: string | null;
  style?: StyleProp<ImageStyle>;
  resizeMode?: 'cover' | 'contain' | 'stretch';
};

/** Loads an authenticated wallet document and renders image or PDF placeholder. */
export function AuthDocumentImage({
  kind,
  id,
  title,
  fileNameHint,
  style,
  resizeMode = 'cover',
}: Props) {
  const [uri, setUri] = useState<string | null>(null);
  const [isPdf, setIsPdf] = useState(false);
  const [ext, setExt] = useState('');
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    setUri(null);
    setIsPdf(false);
    downloadClientDocument(kind, id, title || 'preview', { fileNameHint })
      .then((doc) => {
        if (cancelled) return;
        setExt(doc.ext || '');
        if (doc.isImage) {
          setUri(doc.uri);
          setIsPdf(false);
        } else if (doc.isPdf) {
          setIsPdf(true);
        } else {
          setFailed(true);
          setExt(doc.ext || '');
        }
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
  }, [kind, id, title, fileNameHint]);

  if (loading) {
    return (
      <View style={[styles.fallback, style as any]}>
        <ActivityIndicator color={Colors.gold} />
      </View>
    );
  }

  if (isPdf) {
    return (
      <View style={[styles.fallback, styles.pdfFallback, style as any]}>
        <Text style={styles.pdfBadge}>PDF</Text>
        <Text style={styles.pdfSub}>Tap to view ID</Text>
      </View>
    );
  }

  if (failed || !uri) {
    return (
      <View style={[styles.fallback, style as any]}>
        <Text style={styles.otherBadge}>{ext ? `.${ext.toUpperCase()}` : 'FILE'}</Text>
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
  pdfFallback: {
    backgroundColor: 'rgba(201,162,39,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(201,162,39,0.35)',
  },
  pdfBadge: {
    color: Colors.gold,
    fontWeight: '900',
    fontSize: 22,
    letterSpacing: 1.5,
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
