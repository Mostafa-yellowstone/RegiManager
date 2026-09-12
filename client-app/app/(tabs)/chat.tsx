import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';

import { Colors } from '@/constants/theme';
import { fetchChatMessages, sendChatMessage, waitChatMessages } from '@/lib/api';

export default function ChatScreen() {
  const [messages, setMessages] = useState<any[]>([]);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const lastIdRef = useRef(0);
  const activeRef = useRef(true);
  const listRef = useRef<FlatList>(null);

  const mergeMessages = useCallback((rows: any[]) => {
    if (!rows?.length) return;
    setMessages((prev) => {
      const map = new Map(prev.map((m) => [m.id, m]));
      rows.forEach((m) => map.set(m.id, m));
      const next = Array.from(map.values()).sort((a, b) => a.id - b.id);
      lastIdRef.current = next.length ? next[next.length - 1].id : lastIdRef.current;
      return next;
    });
  }, []);

  const load = useCallback(async () => {
    setError('');
    try {
      const data = await fetchChatMessages();
      const rows = data.results || [];
      setMessages(rows);
      lastIdRef.current = rows.length ? rows[rows.length - 1].id : 0;
    } catch (err: any) {
      setError(err?.message || 'Could not load messages');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      activeRef.current = true;
      setLoading(true);
      load();
      return () => {
        activeRef.current = false;
      };
    }, [load]),
  );

  useEffect(() => {
    let cancelled = false;
    async function loop() {
      while (!cancelled && activeRef.current) {
        try {
          const data = await waitChatMessages(lastIdRef.current, 25);
          if (cancelled) break;
          if (data?.has_new) mergeMessages(data.results || []);
        } catch {
          await new Promise((r) => setTimeout(r, 1200));
        }
      }
    }
    loop();
    return () => {
      cancelled = true;
    };
  }, [mergeMessages]);

  async function onSend() {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setText('');
    try {
      const msg = await sendChatMessage(body);
      mergeMessages([msg]);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    } catch (err: any) {
      setError(err?.message || 'Could not send');
      setText(body);
    } finally {
      setSending(false);
    }
  }

  if (loading && !messages.length) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={Colors.primaryMid} size="large" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={88}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
        ListEmptyComponent={<Text style={styles.empty}>Message your agency here. Replies appear instantly.</Text>}
        renderItem={({ item }) => {
          const mine = item.sender_role === 'client';
          return (
            <View style={[styles.bubble, mine ? styles.mine : styles.theirs]}>
              <Text style={[styles.body, mine && styles.bodyMine]}>{item.body}</Text>
              <Text style={[styles.meta, mine && styles.metaMine]}>
                {item.sender_name || item.sender_role}
              </Text>
            </View>
          );
        }}
      />
      <View style={styles.composer}>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder="Type a message…"
          placeholderTextColor={Colors.mutedLight}
          editable={!sending}
        />
        <Pressable style={[styles.send, sending && { opacity: 0.6 }]} onPress={onSend} disabled={sending}>
          {sending ? <ActivityIndicator color="#fff" /> : <Text style={styles.sendText}>Send</Text>}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#F1F5F9' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { padding: 14, paddingBottom: 20 },
  empty: { color: Colors.muted, textAlign: 'center', marginTop: 40, fontSize: 14 },
  bubble: {
    maxWidth: '82%',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 8,
  },
  mine: { alignSelf: 'flex-end', backgroundColor: Colors.primaryMid },
  theirs: { alignSelf: 'flex-start', backgroundColor: '#fff', borderWidth: 1, borderColor: Colors.border },
  body: { color: Colors.navy, fontSize: 14, lineHeight: 20 },
  bodyMine: { color: '#fff' },
  meta: { marginTop: 4, fontSize: 10, color: Colors.muted },
  metaMine: { color: 'rgba(255,255,255,0.75)' },
  composer: {
    flexDirection: 'row',
    gap: 8,
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: Colors.border,
    backgroundColor: '#fff',
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: Colors.navy,
  },
  send: {
    backgroundColor: Colors.navy,
    borderRadius: 14,
    paddingHorizontal: 16,
    justifyContent: 'center',
    minWidth: 70,
    alignItems: 'center',
  },
  sendText: { color: '#fff', fontWeight: '800' },
  error: { color: Colors.danger, padding: 10, textAlign: 'center', fontWeight: '600' },
});
