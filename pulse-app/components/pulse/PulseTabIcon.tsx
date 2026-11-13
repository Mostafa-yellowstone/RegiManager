import Svg, { Circle, Path } from 'react-native-svg';

import { Colors } from '@/lib/theme';

export type TabKey = 'today' | 'work' | 'money' | 'team' | 'insurance';

type Props = {
  name: TabKey;
  focused: boolean;
  compact?: boolean;
};

export function PulseTabIcon({ name, focused, compact }: Props) {
  const size = compact ? 22 : 26;
  const color = focused ? '#07090C' : Colors.muted;
  const stroke = {
    fill: 'none',
    stroke: color,
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };

  if (name === 'today') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path d="M3 12h3l2-5 4 10 2-5h7" {...stroke} />
      </Svg>
    );
  }

  if (name === 'work') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path d="M8 7h11M8 12h11M8 17h11" {...stroke} />
        <Circle cx="4.5" cy="7" r="1.2" fill={color} />
        <Circle cx="4.5" cy="12" r="1.2" fill={color} />
        <Circle cx="4.5" cy="17" r="1.2" fill={color} />
      </Svg>
    );
  }

  if (name === 'insurance') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path d="M12 3 4.5 6.2V12c0 4.6 3.1 7.9 7.5 9 4.4-1.1 7.5-4.4 7.5-9V6.2L12 3z" {...stroke} />
        <Path d="M9 12.2 11 14.2l4-4.2" {...stroke} />
      </Svg>
    );
  }

  if (name === 'team') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Circle cx="9" cy="8" r="3" {...stroke} />
        <Path d="M3.5 19c.6-2.9 2.8-4.5 5.5-4.5s4.9 1.6 5.5 4.5" {...stroke} />
        <Path d="M15.5 5.3a3 3 0 0 1 0 5.4M17.5 14.7c1.6.6 2.7 2 3 4.3" {...stroke} />
      </Svg>
    );
  }

  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path d="M6 3h12v18l-2.5-1.5L13 21l-2.5-1.5L8 21l-2-1.2V3z" {...stroke} />
      <Path d="M9 8h6M9 11.5h6M9 15h3.5" {...stroke} />
    </Svg>
  );
}
