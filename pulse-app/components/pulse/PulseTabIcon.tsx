import { View } from 'react-native';
import Svg, { Circle, Path, Rect, Text as SvgText } from 'react-native-svg';

import { Colors } from '@/lib/theme';

type TabKey = 'pulse' | 'sales' | 'staff' | 'expenses';

type Props = {
  name: TabKey;
  focused: boolean;
  compact?: boolean;
};

export function PulseTabIcon({ name, focused, compact }: Props) {
  const size = compact ? 22 : 26;
  const color = focused ? Colors.teal : Colors.muted;

  if (name === 'pulse') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path
          d="M3 12h3l2-5 3 10 2-5h6"
          fill="none"
          stroke={color}
          strokeWidth={2.2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
    );
  }

  if (name === 'sales') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Circle cx="12" cy="12" r="9" fill={focused ? Colors.orange : '#FDBA74'} />
        <SvgText
          x="12"
          y="16"
          textAnchor="middle"
          fontSize="11"
          fontWeight="800"
          fill="#fff"
        >
          $
        </SvgText>
      </Svg>
    );
  }

  if (name === 'staff') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Circle cx="12" cy="7" r="2.5" fill={focused ? Colors.blue : '#93C5FD'} />
        <Circle cx="7" cy="8.5" r="2" fill={focused ? Colors.blue : '#93C5FD'} opacity={0.85} />
        <Circle cx="17" cy="8.5" r="2" fill={focused ? Colors.blue : '#93C5FD'} opacity={0.85} />
        <Path
          d="M5 18c.7-2.2 2.4-3.3 4-3.3h6c1.6 0 3.3 1.1 4 3.3"
          fill="none"
          stroke={focused ? Colors.blue : '#93C5FD'}
          strokeWidth={1.8}
          strokeLinecap="round"
        />
      </Svg>
    );
  }

  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      <Path
        d="M7 3h10a1 1 0 0 1 1 1v16l-2-1.2L14 20l-2-1.2L10 20l-2-1.2L6 20V4a1 1 0 0 1 1-1z"
        fill={focused ? Colors.purple : '#D8B4FE'}
      />
      <Rect x="9" y="7" width="6" height="1.3" rx="0.5" fill="#fff" />
      <Rect x="9" y="10" width="6" height="1.3" rx="0.5" fill="#fff" />
      <Rect x="9" y="13" width="4" height="1.3" rx="0.5" fill="#fff" />
    </Svg>
  );
}
