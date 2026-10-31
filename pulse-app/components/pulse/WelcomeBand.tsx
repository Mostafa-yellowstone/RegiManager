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

import { Fonts } from '@/lib/theme';

const QUOTES = [
  'Keep the desk moving. The day pays you back.',
  'Finish one thing, then take the next.',
  'A busy office is a living office.',
  'Your people are the business. Stay close to them.',
  'Small finished jobs build a strong week.',
];

const BLOCKS = ['#C4512F', '#E3A008', '#2E4A7A', '#7A4E8A', '#E07A55', '#C4512F', '#E3A008', '#2E4A7A'];

export function WelcomeBand({ name }: { name: string }) {
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
        backgroundColor: '#241C18',
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
          backgroundColor: 'rgba(36, 28, 24, 0.55)',
        }}
      />
      <View style={{ paddingHorizontal: 18, paddingTop: 28, paddingBottom: 20, gap: 10 }}>
        <Text style={{ fontFamily: Fonts.extrabold, fontSize: 32, color: '#FFFCF8', letterSpacing: -0.6 }}>
          {hello}
        </Text>
        <Animated.Text
          key={quote}
          entering={FadeIn.duration(400)}
          exiting={FadeOut.duration(200)}
          style={{ fontFamily: Fonts.medium, fontSize: 18, lineHeight: 26, color: '#FFF6E8', minHeight: 52 }}
        >
          {QUOTES[quote]}
        </Animated.Text>
      </View>
    </View>
  );
}
