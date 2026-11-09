import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import Animated, {
  Easing,
  FadeIn,
  FadeOut,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { usePulseScale } from '@/lib/responsive';
import { Colors, Fonts } from '@/lib/theme';

const QUOTES = [
  'Keep the desk moving. The day pays you back.',
  'Finish one thing, then take the next.',
  'A busy office is a living office.',
  'Your people are the business. Stay close to them.',
  'Small finished jobs build a strong week.',
];

const BLOCKS = ['#3DDC97', '#4C8DFF', '#F5A524', '#3DDC97', '#4C8DFF', '#F5A524'];

export function WelcomeBand({ name }: { name: string }) {
  const { fs } = usePulseScale();
  const [quote, setQuote] = useState(0);
  const shift = useSharedValue(0);

  useEffect(() => {
    shift.value = withRepeat(withTiming(-360, { duration: 9000, easing: Easing.linear }), -1, false);
  }, [shift]);

  useEffect(() => {
    const timer = setInterval(() => {
      setQuote((current) => (current + 1) % QUOTES.length);
    }, 4000);
    return () => clearInterval(timer);
  }, []);

  const slide = useAnimatedStyle(() => ({
    transform: [{ translateX: shift.value }],
  }));

  const hello = name ? `Welcome, ${name}` : 'Welcome';

  return (
    <View
      style={{
        borderRadius: 24,
        overflow: 'hidden',
        minHeight: 196,
        backgroundColor: '#07090C',
        justifyContent: 'flex-end',
      }}
    >
      <Animated.View
        style={[
          {
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            flexDirection: 'row',
          },
          slide,
        ]}
      >
        {[...BLOCKS, ...BLOCKS].map((color, index) => (
          <View key={`${color}-${index}`} style={{ width: 92, height: 220, backgroundColor: color }} />
        ))}
      </Animated.View>
      <View
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: 150,
          backgroundColor: 'rgba(7, 9, 12, 0.62)',
        }}
      />
      <View style={{ paddingHorizontal: 18, paddingTop: 28, paddingBottom: 20, gap: 10 }}>
        <Text style={{ fontFamily: Fonts.extrabold, fontSize: fs(30), color: '#F4F7FB', letterSpacing: -0.6 }}>
          {hello}
        </Text>
        <Animated.Text
          key={quote}
          entering={FadeIn.duration(400)}
          exiting={FadeOut.duration(200)}
          style={{ fontFamily: Fonts.medium, fontSize: fs(17), lineHeight: fs(24), color: '#E7EDF5', minHeight: fs(52) }}
        >
          {QUOTES[quote]}
        </Animated.Text>
      </View>
    </View>
  );
}
