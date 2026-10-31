import { useIsFetching } from '@tanstack/react-query';
import { useEffect } from 'react';
import { View } from 'react-native';
import Animated, {
  Easing,
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { Colors } from '@/lib/theme';

export function PulseRequestBar() {
  const fetching = useIsFetching();
  const travel = useSharedValue(-120);

  useEffect(() => {
    if (fetching > 0) {
      travel.value = -120;
      travel.value = withRepeat(
        withTiming(360, { duration: 1100, easing: Easing.inOut(Easing.quad) }),
        -1,
        false,
      );
      return;
    }
    cancelAnimation(travel);
    travel.value = -120;
  }, [fetching, travel]);

  const slide = useAnimatedStyle(() => ({
    transform: [{ translateX: travel.value }],
  }));

  return (
    <View
      accessibilityLabel="RegiManager Pulse"
      style={{
        height: fetching > 0 ? 3 : 0,
        backgroundColor: Colors.tealSoft,
        overflow: 'hidden',
      }}
    >
      <Animated.View
        style={[
          {
            width: 96,
            height: 3,
            borderRadius: 2,
            backgroundColor: Colors.tealDeep,
          },
          slide,
        ]}
      />
    </View>
  );
}
