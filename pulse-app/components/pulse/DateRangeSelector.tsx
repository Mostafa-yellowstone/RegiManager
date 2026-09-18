import { Pressable, ScrollView, Text, View } from 'react-native';

import { hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import type { DateRangePreset } from '@/types/models';

const OPTIONS: Array<{ id: DateRangePreset; label: string }> = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'week', label: 'This Week' },
  { id: 'month', label: 'This Month' },
  { id: 'ytd', label: 'YTD' },
];

type Props = {
  value: DateRangePreset;
  onChange: (preset: DateRangePreset) => void;
};

export function DateRangeSelector({ value, onChange }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }}>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        {OPTIONS.map((opt) => {
          const active = opt.id === value;
          return (
            <Pressable
              key={opt.id}
              onPress={async () => {
                await hapticSelection();
                onChange(opt.id);
              }}
              style={{
                borderRadius: 999,
                paddingHorizontal: 14,
                paddingVertical: 9,
                backgroundColor: active ? Colors.teal : Colors.white,
                borderWidth: 1,
                borderColor: active ? Colors.teal : Colors.border,
              }}
              android_ripple={{ color: 'rgba(13,148,136,0.12)' }}
            >
              <Text
                style={{
                  fontFamily: Fonts.bold,
                  fontSize: 12,
                  color: active ? Colors.white : Colors.navy,
                }}
              >
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </ScrollView>
  );
}
