import { Text, View } from 'react-native';

import { formatMoney } from '@/lib/format';
import type { TargetProgressRow } from '@/types/models';

type Props = {
  items: TargetProgressRow[];
};

export function TargetProgress({ items }: Props) {
  return (
    <View className="gap-3">
      {items.map((item) => (
        <View key={`${item.period}-${item.type}`} className="rounded-2xl border border-border bg-white p-4">
          <View className="mb-2 flex-row items-center justify-between">
            <Text className="text-caption font-bold uppercase tracking-wide text-muted">
              {item.period} target
            </Text>
            <Text className="text-caption font-semibold text-navy">{item.progress_pct}%</Text>
          </View>
          <View className="h-2 overflow-hidden rounded-full bg-navy-soft">
            <View
              className="h-full rounded-full bg-navy"
              style={{ width: `${Math.min(100, item.progress_pct)}%` }}
            />
          </View>
          <View className="mt-3 flex-row items-end justify-between">
            <Text className="text-body font-semibold text-ink">
              {formatMoney(item.actual_amount)}
              <Text className="font-normal text-muted"> / {formatMoney(item.target_amount)}</Text>
            </Text>
            <Text className="text-caption text-muted">
              {item.run_rate_label}: {formatMoney(item.run_rate_amount, true)}
            </Text>
          </View>
        </View>
      ))}
    </View>
  );
}
