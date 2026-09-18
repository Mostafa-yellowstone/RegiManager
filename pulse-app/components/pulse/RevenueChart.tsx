import { useMemo } from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient as SvgGradient, Path, Stop } from 'react-native-svg';

import { formatMoney } from '@/lib/format';
import { Colors } from '@/lib/theme';

type Props = {
  data: Array<{ timestamp: number; value: number }>;
};

const WIDTH = 340;
const HEIGHT = 180;
const PAD_X = 12;
const PAD_Y = 16;

export function RevenueChart({ data }: Props) {
  const { area, dots, yLabels, xLabels } = useMemo(() => {
    if (!data.length) {
      return {
        area: '',
        dots: [] as Array<{ x: number; y: number }>,
        yLabels: [] as string[],
        xLabels: [] as string[],
      };
    }
    const values = data.map((d) => d.value);
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 1);
    const span = Math.max(1, max - min);
    const points = data.map((d, i) => {
      const x = PAD_X + (i / Math.max(1, data.length - 1)) * (WIDTH - PAD_X * 2);
      const y = HEIGHT - PAD_Y - ((d.value - min) / span) * (HEIGHT - PAD_Y * 2);
      return { x, y, value: d.value, timestamp: d.timestamp };
    });
    const areaPath = `M ${points[0].x} ${HEIGHT - PAD_Y} ${points
      .map((p) => `L ${p.x} ${p.y}`)
      .join(' ')} L ${points[points.length - 1].x} ${HEIGHT - PAD_Y} Z`;

    const yLabels = [max, (max + min) / 2, min].map((v) => formatMoney(v, true));
    const spanMs =
      points.length > 1 ? points[points.length - 1].timestamp - points[0].timestamp : 0;
    const useMonthLabels = spanMs > 1000 * 60 * 60 * 24 * 40;
    const step = Math.max(1, Math.floor((points.length - 1) / 3));
    const xLabels = [0, step, Math.min(points.length - 1, step * 2), points.length - 1]
      .filter((v, i, arr) => arr.indexOf(v) === i)
      .map((idx) => {
        const d = new Date(points[idx].timestamp);
        if (Number.isNaN(d.getTime())) return '';
        return useMonthLabels
          ? d.toLocaleDateString(undefined, { month: 'short' })
          : d.toLocaleDateString(undefined, { weekday: 'short' });
      });

    return { area: areaPath, dots: points, yLabels, xLabels };
  }, [data]);

  if (!data.length) {
    return (
      <View className="h-48 items-center justify-center rounded-2xl bg-white">
        <Text className="text-caption text-muted">No chart data</Text>
      </View>
    );
  }

  const linePath = dots.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  return (
    <View
      className="rounded-2xl bg-white p-4"
      style={{
        borderWidth: 1,
        borderColor: Colors.border,
        shadowColor: '#0F3D4C',
        shadowOpacity: 0.06,
        shadowRadius: 12,
        shadowOffset: { width: 0, height: 4 },
        elevation: 2,
      }}
    >
      <View className="mb-3 flex-row items-center justify-between">
        <Text className="text-caption font-bold uppercase tracking-wide text-muted">
          Profit trend
        </Text>
      </View>

      <View className="flex-row">
        <View className="mr-1 justify-between py-1" style={{ width: 42, height: HEIGHT }}>
          {yLabels.map((label) => (
            <Text key={label} className="text-[10px] text-muted">
              {label}
            </Text>
          ))}
        </View>
        <View className="flex-1">
          <Svg width="100%" height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
            <Defs>
              <SvgGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0%" stopColor={Colors.teal} stopOpacity="0.28" />
                <Stop offset="100%" stopColor={Colors.teal} stopOpacity="0.02" />
              </SvgGradient>
            </Defs>
            <Path d={area} fill="url(#areaFill)" />
            <Path
              d={linePath}
              fill="none"
              stroke={Colors.teal}
              strokeWidth={2.5}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            {dots.map((p) => (
              <Circle
                key={`${p.x}-${p.y}`}
                cx={p.x}
                cy={p.y}
                r={3.5}
                fill={Colors.white}
                stroke={Colors.teal}
                strokeWidth={2}
              />
            ))}
          </Svg>
          <View className="mt-1 flex-row justify-between px-1">
            {xLabels.map((label, i) => (
              <Text key={`${label}-${i}`} className="text-[10px] text-muted">
                {label}
              </Text>
            ))}
          </View>
        </View>
      </View>
    </View>
  );
}
