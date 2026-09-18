import { Pressable, Text, View } from 'react-native';

import { formatMoney, formatPct } from '@/lib/format';
import { Fonts, MetricAccents, type MetricAccent } from '@/lib/theme';
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
  /** Clarifies what the number means (profit vs cash). */
  hint?: string;
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
  hint,
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
        numberOfLines={1}
        style={{
          fontFamily: Fonts.bold,
          fontSize: 11,
          letterSpacing: 0.6,
          textTransform: 'uppercase',
          color: theme.deep,
        }}
      >
        {label}
      </Text>
      <Text
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.75}
        style={{
          marginTop: 8,
          fontFamily: Fonts.extrabold,
          fontSize: 22,
          color: '#0F1F1C',
        }}
      >
        {display}
      </Text>
      {hint ? (
        <Text
          numberOfLines={1}
          style={{
            marginTop: 4,
            fontFamily: Fonts.semibold,
            fontSize: 10,
            color: theme.deep,
            opacity: 0.75,
          }}
        >
          {hint}
        </Text>
      ) : null}
      <View style={{ marginTop: 'auto', paddingTop: 12, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        {metaText ? (
          <View
            style={{
              borderRadius: 999,
              paddingHorizontal: 8,
              paddingVertical: 4,
              backgroundColor: theme.soft,
              maxWidth: '52%',
            }}
          >
            <Text numberOfLines={1} style={{ fontFamily: Fonts.bold, fontSize: 10, color: theme.deep }}>
              {metaText}
            </Text>
          </View>
        ) : (
          <View style={{ flex: 1 }} />
        )}
        {badge ? (
          <View
            style={{
              borderRadius: 999,
              paddingHorizontal: 8,
              paddingVertical: 4,
              backgroundColor: theme.soft,
              flexShrink: 1,
            }}
          >
            <Text numberOfLines={1} style={{ fontFamily: Fonts.extrabold, fontSize: 10, color: theme.main }}>
              {formatPct(badge.delta_pct)}
              {badge.label ? ` ${badge.label}` : ''}
            </Text>
          </View>
        ) : null}
      </View>
    </>
  );

  const cardStyle = {
    borderWidth: 1,
    borderColor: theme.border,
    borderRadius: 16,
    backgroundColor: '#FFFFFF',
    padding: 14,
    minHeight: 124,
    width: '100%' as const,
    shadowColor: '#0B3D3A',
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  };

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={cardStyle}
        android_ripple={{ color: 'rgba(13,148,136,0.08)' }}
      >
        {body}
      </Pressable>
    );
  }

  return <View style={cardStyle}>{body}</View>;
}
