import { View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { useEffect } from 'react';

type Props = {
  height?: number;
  className?: string;
};

export function SkeletonBlock({ height = 88, className = '' }: Props) {
  const opacity = useSharedValue(0.45);

  useEffect(() => {
    opacity.value = withRepeat(withTiming(1, { duration: 700 }), -1, true);
  }, [opacity]);

  const style = useAnimatedStyle(() => ({ opacity: opacity.value }));

  return (
    <Animated.View style={[{ height }, style]} className={`rounded-2xl bg-navy-soft ${className}`}>
      <View />
    </Animated.View>
  );
}
