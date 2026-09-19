import { View } from 'react-native';
import Svg, { Circle, Path, Rect, Text as SvgText } from 'react-native-svg';

import { Colors } from '@/lib/theme';

export type TabKey = 'pulse' | 'sales' | 'insurance' | 'staff' | 'expenses';

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
        <SvgText x="12" y="16" textAnchor="middle" fontSize="11" fontWeight="800" fill="#fff">
          $
        </SvgText>
      </Svg>
    );
  }

  if (name === 'insurance') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path
          d="M12 3 4 6.5V12c0 5 3.4 8.6 8 9.5 4.6-.9 8-4.5 8-9.5V6.5L12 3z"
          fill={focused ? Colors.green : '#6EE7B7'}
        />
        <Path
          d="M9.2 12.2 11 14l3.8-4"
          fill="none"
          stroke="#fff"
          strokeWidth={1.8}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
    );
  }

  if (name === 'staff') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Circle cx="12" cy="7" r="2.5" fill={focused ? Colors.teal : '#5EEAD4'} />
        <Circle cx="7" cy="8.5" r="2" fill={focused ? Colors.teal : '#5EEAD4'} opacity={0.85} />
        <Circle cx="17" cy="8.5" r="2" fill={focused ? Colors.teal : '#5EEAD4'} opacity={0.85} />
        <Path
          d="M5 18c.7-2.2 2.4-3.3 4-3.3h6c1.6 0 3.3 1.1 4 3.3"
          fill="none"
          stroke={focused ? Colors.teal : '#5EEAD4'}
          strokeWidth={1.8}
          strokeLinecap="round"
        />
      </Svg>
    );
  }

  return (
    <View>
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path
          d="M7 3h10a1 1 0 0 1 1 1v16l-2-1.2L14 20l-2-1.2L10 20l-2-1.2L6 20V4a1 1 0 0 1 1-1z"
          fill={focused ? Colors.purple : '#99F6E4'}
        />
        <Rect x="9" y="7" width="6" height="1.3" rx="0.5" fill="#fff" />
        <Rect x="9" y="10" width="6" height="1.3" rx="0.5" fill="#fff" />
        <Rect x="9" y="13" width="4" height="1.3" rx="0.5" fill="#fff" />
      </Svg>
    </View>
  );
}
