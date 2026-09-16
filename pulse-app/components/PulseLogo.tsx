import React, { useEffect } from 'react';
import { Image, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import { Colors } from '@/lib/theme';

type LogoSize = 'small' | 'medium' | 'large';

type PulseLogoProps = {
  size?: LogoSize;
  showText?: boolean;
  showTagline?: boolean;
  animated?: boolean;
  textColor?: string;
  taglineColor?: string;
};

const SIZES: Record<LogoSize, { logo: number; title: number; tagline: number }> = {
  small: { logo: 56, title: 18, tagline: 11 },
  medium: { logo: 96, title: 28, tagline: 13 },
  large: { logo: 132, title: 34, tagline: 14 },
};

export function PulseLogo({
  size = 'medium',
  showText = true,
  showTagline = false,
  animated = true,
  textColor = Colors.white,
  taglineColor = 'rgba(255,255,255,0.65)',
}: PulseLogoProps) {
  const scale = useSharedValue(animated ? 0.72 : 1);
  const opacity = useSharedValue(animated ? 0 : 1);
  const pulse = useSharedValue(1);
  const textY = useSharedValue(animated ? 16 : 0);
  const textOpacity = useSharedValue(animated ? 0 : 1);

  useEffect(() => {
    if (!animated) return;
    scale.value = withSpring(1, { damping: 14, stiffness: 120 });
    opacity.value = withTiming(1, { duration: 420 });
    textY.value = withDelay(280, withSpring(0, { damping: 16, stiffness: 100 }));
    textOpacity.value = withDelay(280, withTiming(1, { duration: 380 }));
    pulse.value = withDelay(
      700,
      withRepeat(
        withSequence(
          withTiming(1.045, { duration: 1400, easing: Easing.inOut(Easing.ease) }),
          withTiming(1, { duration: 1400, easing: Easing.inOut(Easing.ease) }),
        ),
        -1,
        false,
      ),
    );
  }, [animated, opacity, pulse, scale, textOpacity, textY]);

  const markStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ scale: scale.value * pulse.value }],
  }));

  const textStyle = useAnimatedStyle(() => ({
    opacity: textOpacity.value,
    transform: [{ translateY: textY.value }],
  }));

  const dims = SIZES[size];

  return (
    <View style={{ alignItems: 'center' }}>
      <Animated.View style={markStyle}>
        <Image
          source={require('../assets/images/logo.png')}
          style={{
            width: dims.logo,
            height: dims.logo,
            borderRadius: dims.logo / 2,
          }}
          resizeMode="cover"
          accessibilityLabel="RegiManager Pulse"
        />
      </Animated.View>
      {showText ? (
        <Animated.View style={[{ alignItems: 'center', marginTop: 14 }, textStyle]}>
          <Text
            style={{
              color: textColor,
              fontSize: dims.title,
              fontWeight: '800',
              letterSpacing: -0.5,
            }}
          >
            REGIMANAGER
          </Text>
          <Text
            style={{
              marginTop: -2,
              color: Colors.gold,
              fontSize: Math.max(12, dims.title * 0.48),
              fontWeight: '800',
              letterSpacing: 0.5,
            }}
          >
            Pulse
          </Text>
          {showTagline ? (
            <Text
              style={{
                marginTop: 4,
                color: taglineColor,
                fontSize: dims.tagline,
                fontWeight: '600',
                letterSpacing: 0.4,
              }}
            >
              Owner insights · Live CRM
            </Text>
          ) : null}
        </Animated.View>
      ) : null}
    </View>
  );
}
