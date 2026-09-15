import { Pressable, ScrollView, Text, View } from 'react-native';

import { hapticSelection } from '@/lib/haptics';
import type { DateRangePreset } from '@/types/models';

const OPTIONS: Array<{ id: DateRangePreset; label: string }> = [
  { id: 'today', label: 'Today' },
  { id: 'yesterday', label: 'Yesterday' },
  { id: 'week', label: 'This Week' },
  { id: 'month', label: 'This Month' },
  { id: 'ytd', label: 'YTD' },
  { id: 'custom', label: 'Custom' },
];

type Props = {
  value: DateRangePreset;
  onChange: (preset: DateRangePreset) => void;
};

export function DateRangeSelector({ value, onChange }: Props) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} className="grow-0">
      <View className="flex-row gap-2 px-0">
        {OPTIONS.map((opt) => {
          const active = opt.id === value;
          return (
            <Pressable
              key={opt.id}
              onPress={async () => {
                await hapticSelection();
                onChange(opt.id);
              }}
              className={`rounded-full border px-4 py-2 ${
                active ? 'border-navy bg-navy' : 'border-border bg-white'
              }`}
              android_ripple={{ color: 'rgba(26,43,72,0.12)' }}
            >
              <Text className={`text-caption font-bold ${active ? 'text-white' : 'text-navy'}`}>
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </ScrollView>
  );
}
