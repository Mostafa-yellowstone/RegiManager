import { useMemo } from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle, Polyline, Rect } from 'react-native-svg';

import { formatMoney } from '@/lib/format';
import { Colors } from '@/lib/theme';

type Props = {
  data: Array<{ timestamp: number; value: number }>;
};

const WIDTH = 320;
const HEIGHT = 160;
const PAD = 12;

export function RevenueChart({ data }: Props) {
  const points = useMemo(() => {
    if (!data.length) return '';
    const values = data.map((d) => d.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = Math.max(1, max - min);
    return data
      .map((d, i) => {
        const x = PAD + (i / Math.max(1, data.length - 1)) * (WIDTH - PAD * 2);
        const y = HEIGHT - PAD - ((d.value - min) / span) * (HEIGHT - PAD * 2);
        return `${x},${y}`;
      })
      .join(' ');
  }, [data]);

  const last = data[data.length - 1];
  const first = data[0];

  if (!data.length) {
    return (
      <View className="h-44 items-center justify-center rounded-2xl border border-border bg-white">
        <Text className="text-caption text-muted">No chart data</Text>
      </View>
    );
  }

  return (
    <View className="rounded-2xl border border-border bg-white p-4">
      <Text className="mb-2 text-caption font-bold uppercase tracking-wide text-muted">
        Revenue trend
      </Text>
      <View className="items-center">
        <Svg width="100%" height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
          <Rect x={0} y={0} width={WIDTH} height={HEIGHT} fill={Colors.cream} rx={12} />
          <Polyline
            points={points}
            fill="none"
            stroke={Colors.navy}
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {data.map((d, i) => {
            const values = data.map((x) => x.value);
            const min = Math.min(...values);
            const max = Math.max(...values);
            const span = Math.max(1, max - min);
            const x = PAD + (i / Math.max(1, data.length - 1)) * (WIDTH - PAD * 2);
            const y = HEIGHT - PAD - ((d.value - min) / span) * (HEIGHT - PAD * 2);
            if (i !== data.length - 1) return null;
            return <Circle key={d.timestamp} cx={x} cy={y} r={4} fill={Colors.gold} />;
          })}
        </Svg>
      </View>
      <View className="mt-2 flex-row justify-between">
        <Text className="text-caption text-muted">{formatMoney(first?.value ?? 0, true)}</Text>
        <Text className="text-caption font-bold text-navy">
          {formatMoney(last?.value ?? 0, true)}
        </Text>
      </View>
    </View>
  );
}
