import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, StyleSheet, View, type ImageStyle, type StyleProp } from 'react-native';

import { Colors } from '@/constants/theme';
import { downloadClientDocument } from '@/lib/openDocument';

type Props = {
  kind: string;
  id: number | string;
  title?: string;
  style?: StyleProp<ImageStyle>;
  resizeMode?: 'cover' | 'contain' | 'stretch';
};

/** Loads an authenticated wallet document and renders it as an image when possible. */
export function AuthDocumentImage({ kind, id, title, style, resizeMode = 'cover' }: Props) {
  const [uri, setUri] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    setUri(null);
    downloadClientDocument(kind, id, title || 'preview')
      .then((doc) => {
        if (cancelled) return;
        if (doc.isImage) setUri(doc.uri);
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
    return <View style={[styles.fallback, style as any]} />;
  }

  return <Image source={{ uri }} style={style} resizeMode={resizeMode} />;
}

const styles = StyleSheet.create({
  fallback: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
