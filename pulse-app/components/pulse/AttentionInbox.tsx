import { Pressable, Text, View } from 'react-native';

import { Colors } from '@/lib/theme';
import type { AttentionItem, AttentionLevel } from '@/lib/ownerInsights';

type Props = {
  items: AttentionItem[];
  onOpen: (item: AttentionItem) => void;
};

function levelStyle(level: AttentionLevel) {
  if (level === 'critical') {
    return { bg: '#FEE2E2', fg: '#991B1B', label: 'Urgent' };
  }
  if (level === 'warning') {
    return { bg: Colors.orangeSoft, fg: Colors.orangeDeep, label: 'Watch' };
  }
  return { bg: Colors.tealSoft, fg: Colors.tealDeep, label: 'Info' };
}

export function AttentionInbox({ items, onOpen }: Props) {
  if (!items.length) {
    return (
      <View
        className="rounded-2xl bg-white px-4 py-3"
        style={{ borderWidth: 1, borderColor: Colors.border }}
      >
        <Text className="text-title text-navy">Needs attention</Text>
        <Text className="mt-1 text-caption text-muted">
          Nothing urgent right now — profit, cash, and staff look calm for this range.
        </Text>
      </View>
    );
  }

  return (
    <View
      className="rounded-2xl bg-white px-4 py-3"
      style={{ borderWidth: 1, borderColor: Colors.border }}
    >
      <Text className="mb-2 text-title text-navy">Needs attention</Text>
      <View className="gap-2">
        {items.map((item) => {
          const tone = levelStyle(item.level);
          return (
            <Pressable
              key={item.id}
              onPress={() => onOpen(item)}
              className="rounded-xl px-3 py-3"
              style={{ backgroundColor: Colors.cream, borderWidth: 1, borderColor: Colors.border }}
              android_ripple={{ color: 'rgba(15,61,76,0.06)' }}
            >
              <View className="mb-1 flex-row items-center justify-between gap-2">
                <Text className="flex-1 text-body font-bold text-navy">{item.title}</Text>
                <View className="rounded-full px-2 py-0.5" style={{ backgroundColor: tone.bg }}>
                  <Text className="text-[10px] font-extrabold" style={{ color: tone.fg }}>
                    {tone.label}
                  </Text>
                </View>
              </View>
              <Text className="text-caption text-muted">{item.body}</Text>
              <Text className="mt-2 text-[11px] font-bold text-teal">Open →</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
