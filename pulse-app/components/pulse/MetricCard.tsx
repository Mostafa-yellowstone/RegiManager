import { Pressable, Text, View } from 'react-native';

import { formatMoney, formatPct } from '@/lib/format';
import { MetricAccents, type MetricAccent } from '@/lib/theme';
import type { ComparativeBadge } from '@/types/models';

type Props = {
  label: string;
  value: number;
  format?: 'money' | 'pct' | 'count';
  badge?: ComparativeBadge;
  accent?: MetricAccent;
  /** Secondary stat chip, e.g. "128 records" or "42 bound". */
  metaLabel?: string;
  metaValue?: string | number;
  onPress?: () => void;
};

export function MetricCard({
  label,
  value,
  format = 'money',
  badge,
  accent = 'teal',
  metaLabel,
  metaValue,
  onPress,
}: Props) {
  const theme = MetricAccents[accent];
  const display =
    format === 'pct'
      ? `${value.toFixed(1)}%`
      : format === 'count'
        ? String(value)
        : formatMoney(value);

  const metaText =
    metaValue != null && metaLabel
      ? `${metaValue} ${metaLabel}`
      : metaLabel || (metaValue != null ? String(metaValue) : null);

  const body = (
    <>
      <Text
        className="text-[11px] font-bold uppercase tracking-wide"
        style={{ color: theme.deep }}
        numberOfLines={1}
      >
        {label}
      </Text>
      <Text className="mt-2 text-[24px] font-extrabold text-ink" numberOfLines={1}>
        {display}
      </Text>
      <View className="mt-auto pt-3 flex-row items-center justify-between">
        {metaText ? (
          <View className="rounded-full px-2.5 py-1" style={{ backgroundColor: theme.soft }}>
            <Text className="text-[11px] font-bold" style={{ color: theme.deep }}>
              {metaText}
            </Text>
          </View>
        ) : (
          <View />
        )}
        {badge ? (
          <Text className="text-[11px] font-semibold" style={{ color: theme.main }}>
            {formatPct(badge.delta_pct)}
          </Text>
        ) : null}
      </View>
    </>
  );

  const cardStyle = {
    borderWidth: 1,
    borderColor: theme.border,
    shadowColor: '#0F3D4C',
    shadowOpacity: 0.07,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
    minHeight: 118,
  } as const;

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        className="min-w-[46%] flex-1 rounded-2xl bg-white p-4"
        style={cardStyle}
        android_ripple={{ color: 'rgba(15,61,76,0.06)' }}
      >
        {body}
      </Pressable>
    );
  }

  return (
    <View className="min-w-[46%] flex-1 rounded-2xl bg-white p-4" style={cardStyle}>
      {body}
    </View>
  );
}
