import { Text, View } from 'react-native';

import { formatMoney, formatPct } from '@/lib/format';

type Props = {
  label: string;
  value: number;
  format?: 'money' | 'pct';
  deltaPct?: number;
  deltaLabel?: string;
  emphasize?: boolean;
};

export function MetricCard({
  label,
  value,
  format = 'money',
  deltaPct,
  deltaLabel = 'vs prior',
  emphasize,
}: Props) {
  const display = format === 'pct' ? `${value.toFixed(1)}%` : formatMoney(value);
  const up = (deltaPct ?? 0) >= 0;

  return (
    <View
      className={`flex-1 min-w-[46%] rounded-2xl border border-border bg-white p-4 ${
        emphasize ? 'border-navy/20' : ''
      }`}
    >
      <Text className="text-caption uppercase tracking-wide text-muted">{label}</Text>
      <Text className="mt-2 text-[22px] font-extrabold text-navy" numberOfLines={1}>
        {display}
      </Text>
      {deltaPct != null ? (
        <View className="mt-3 self-start rounded-md bg-navy-soft px-2 py-1">
          <Text className={`text-caption font-semibold ${up ? 'text-success' : 'text-danger'}`}>
            {formatPct(deltaPct)} {deltaLabel}
          </Text>
        </View>
      ) : null}
    </View>
  );
}
