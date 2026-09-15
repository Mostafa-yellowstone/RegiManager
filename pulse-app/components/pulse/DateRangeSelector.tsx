import { Pressable, ScrollView, Text, View } from 'react-native';

import { hapticSelection } from '@/lib/haptics';
import { Colors } from '@/lib/theme';
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
    <ScrollView horizontal showsHorizontalScrollIndicator={false} className="grow-0">
      <View className="flex-row gap-2">
        {OPTIONS.map((opt) => {
          const active = opt.id === value;
          return (
            <Pressable
              key={opt.id}
              onPress={async () => {
                await hapticSelection();
                onChange(opt.id);
              }}
              className="rounded-full px-4 py-2.5"
              style={{
                backgroundColor: active ? Colors.navy : Colors.white,
                borderWidth: 1,
                borderColor: active ? Colors.navy : Colors.border,
              }}
              android_ripple={{ color: 'rgba(13,148,136,0.12)' }}
            >
              <Text
                className="text-caption font-bold"
                style={{ color: active ? '#fff' : Colors.navy }}
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
