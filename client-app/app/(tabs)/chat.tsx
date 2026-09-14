import { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  AppState,
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

import { Colors, Radius } from '@/constants/theme';
import { fetchChatMessages, sendChatMessage, waitChatMessages } from '@/lib/api';

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

export default function ChatScreen() {
  const [messages, setMessages] = useState<any[]>([]);
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const lastIdRef = useRef(0);
  const pauseWaitRef = useRef(false);
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

  /**
   * Long-poll must start on every focus. Leaving the Messages tab used to kill the
   * loop without restarting it, so CRM → app messages only appeared after a
   * leave/re-enter (history reload). App → CRM stayed instant via staff wake.
   */
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      let controller = new AbortController();

      const runLoop = async () => {
        while (!cancelled) {
          if (AppState.currentState !== 'active') {
            await sleep(400);
            continue;
          }
          if (pauseWaitRef.current) {
            await sleep(200);
            continue;
          }
          if (controller.signal.aborted) {
            controller = new AbortController();
          }
          try {
            const data = await waitChatMessages(lastIdRef.current, 12, controller.signal);
            if (cancelled) break;
            if (data?.reload) {
              const rows = data.results || [];
              setMessages(rows);
              lastIdRef.current = rows.length ? rows[rows.length - 1].id : 0;
              setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 40);
            } else if (data?.has_new) {
              mergeMessages(data.results || []);
              setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 40);
            }
          } catch (err: any) {
            if (cancelled) break;
            if (err?.name === 'AbortError') {
              await sleep(150);
              continue;
            }
            await sleep(1000);
          }
        }
      };

      setLoading(true);
      load().finally(() => {
        if (!cancelled) runLoop();
      });

      const appSub = AppState.addEventListener('change', (state) => {
        if (state !== 'active') {
          controller.abort();
        } else if (!cancelled) {
          load();
        }
      });

      return () => {
        cancelled = true;
        controller.abort();
        appSub.remove();
      };
    }, [load, mergeMessages]),
  );

  async function onSend() {
    const body = text.trim();
    if (!body || sending) return;
    setSending(true);
    setText('');
    pauseWaitRef.current = true;
    try {
      const msg = await sendChatMessage(body);
      mergeMessages([msg]);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
      setError('');
    } catch (err: any) {
      setError(err?.message || 'Could not send');
      setText(body);
    } finally {
      pauseWaitRef.current = false;
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
      <View style={styles.agentBar}>
        <View style={styles.agentAvatar}>
          <Text style={styles.agentAvatarText}>A</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.agentTitle}>Your agency</Text>
          <Text style={styles.agentSub}>Live · replies appear instantly</Text>
        </View>
        <View style={styles.liveDot} />
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => String(item.id)}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
        ListEmptyComponent={
          <Text style={styles.empty}>Message your agency here. Replies appear instantly.</Text>
        }
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
  screen: { flex: 1, backgroundColor: Colors.cream },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.cream },
  agentBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: Colors.white,
    borderBottomWidth: 1,
    borderBottomColor: Colors.border,
  },
  agentAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: Colors.navy,
    alignItems: 'center',
    justifyContent: 'center',
  },
  agentAvatarText: { color: Colors.gold, fontWeight: '800', fontSize: 14 },
  agentTitle: { fontWeight: '800', color: Colors.navy, fontSize: 14 },
  agentSub: { color: Colors.muted, fontSize: 11, marginTop: 1 },
  liveDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: Colors.success },
  list: { padding: 14, paddingBottom: 20 },
  empty: { color: Colors.muted, textAlign: 'center', marginTop: 40, fontSize: 14 },
  bubble: {
    maxWidth: '82%',
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 8,
  },
  mine: { alignSelf: 'flex-end', backgroundColor: Colors.navy },
  theirs: {
    alignSelf: 'flex-start',
    backgroundColor: Colors.white,
    borderWidth: 1,
    borderColor: Colors.border,
  },
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
    backgroundColor: Colors.white,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: Colors.border,
    borderRadius: Radius.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    color: Colors.navy,
    backgroundColor: Colors.cream,
  },
  send: {
    backgroundColor: Colors.chatOrange,
    borderRadius: Radius.md,
    paddingHorizontal: 16,
    justifyContent: 'center',
    minWidth: 70,
    alignItems: 'center',
  },
  sendText: { color: '#fff', fontWeight: '800' },
  error: { color: Colors.danger, padding: 10, textAlign: 'center', fontWeight: '600' },
});
