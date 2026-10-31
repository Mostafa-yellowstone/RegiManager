import { View } from 'react-native';
import Svg, { Circle, Path, Rect, Text as SvgText } from 'react-native-svg';

import { Colors } from '@/lib/theme';

export type TabKey = 'today' | 'work' | 'money' | 'team' | 'insurance';

type Props = {
  name: TabKey;
  focused: boolean;
  compact?: boolean;
};

export function PulseTabIcon({ name, focused, compact }: Props) {
  const size = compact ? 22 : 26;
  const color = focused ? Colors.teal : Colors.muted;

  if (name === 'today') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Circle cx="12" cy="12" r="8" fill="none" stroke={color} strokeWidth={2} />
        <Path d="M12 8v4l3 2" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" />
      </Svg>
    );
  }

  if (name === 'work') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path
          d="M8 7h11M8 12h11M8 17h11"
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
        />
        <Circle cx="4.5" cy="7" r="1.2" fill={color} />
        <Circle cx="4.5" cy="12" r="1.2" fill={color} />
        <Circle cx="4.5" cy="17" r="1.2" fill={color} />
      </Svg>
    );
  }

  if (name === 'insurance') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Path
          d="M12 3 4 6.5V12c0 5 3.4 8.6 8 9.5 4.6-.9 8-4.5 8-9.5V6.5L12 3z"
          fill={focused ? Colors.teal : '#E7C3B6'}
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

  if (name === 'team') {
    return (
      <Svg width={size} height={size} viewBox="0 0 24 24">
        <Circle cx="12" cy="7" r="2.5" fill={focused ? Colors.teal : '#E7C3B6'} />
        <Circle cx="7" cy="8.5" r="2" fill={focused ? Colors.teal : '#E7C3B6'} opacity={0.85} />
        <Circle cx="17" cy="8.5" r="2" fill={focused ? Colors.teal : '#E7C3B6'} opacity={0.85} />
        <Path
          d="M5 18c.7-2.2 2.4-3.3 4-3.3h6c1.6 0 3.3 1.1 4 3.3"
          fill="none"
          stroke={focused ? Colors.teal : '#E7C3B6'}
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
          fill={focused ? Colors.teal : '#E7C3B6'}
        />
        <Rect x="9" y="7" width="6" height="1.3" rx="0.5" fill="#fff" />
        <Rect x="9" y="10" width="6" height="1.3" rx="0.5" fill="#fff" />
        <Rect x="9" y="13" width="4" height="1.3" rx="0.5" fill="#fff" />
      </Svg>
    </View>
  );
}
