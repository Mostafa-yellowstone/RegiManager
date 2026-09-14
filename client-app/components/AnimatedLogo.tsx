import React, { useEffect } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
  Easing,
} from 'react-native-reanimated';

import { Colors } from '@/constants/theme';

interface AnimatedLogoProps {
  size?: 'small' | 'medium' | 'large';
  showText?: boolean;
  showTagline?: boolean;
  animated?: boolean;
  textColor?: string;
}

export function AnimatedLogo({
  size = 'medium',
  showText = true,
  showTagline = true,
  animated = true,
  textColor,
}: AnimatedLogoProps) {
  const scale = useSharedValue(animated ? 0.3 : 1);
  const opacity = useSharedValue(animated ? 0 : 1);
  const pulse = useSharedValue(1);
  const textTranslateY = useSharedValue(animated ? 20 : 0);
  const textOpacity = useSharedValue(animated ? 0 : 1);

  useEffect(() => {
    if (!animated) return;

    scale.value = 0.3;
    opacity.value = 0;
    textTranslateY.value = 20;
    textOpacity.value = 0;

    scale.value = withSpring(1, { damping: 12, stiffness: 100 });
    opacity.value = withTiming(1, { duration: 500 });

    textTranslateY.value = withDelay(
      450,
      withSpring(0, { damping: 14, stiffness: 90 }),
    );
    textOpacity.value = withDelay(450, withTiming(1, { duration: 400 }));

    pulse.value = withDelay(
      800,
      withRepeat(
        withSequence(
          withTiming(1.04, { duration: 1500, easing: Easing.inOut(Easing.ease) }),
          withTiming(1.0, { duration: 1500, easing: Easing.inOut(Easing.ease) }),
        ),
        -1,
        true,
      ),
    );
  }, [animated]);

  const containerAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value * pulse.value }],
    opacity: opacity.value,
  }));

  const textAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: textTranslateY.value }],
    opacity: textOpacity.value,
  }));

  const dimensions = {
    small: { logoSize: 56, titleSize: 20, subtitleSize: 10 },
    medium: { logoSize: 88, titleSize: 26, subtitleSize: 13 },
    large: { logoSize: 120, titleSize: 32, subtitleSize: 15 },
  }[size];

  const brandTextColor = textColor || Colors.white;

  return (
    <View style={styles.outerWrap}>
      <Animated.View style={[styles.logoFrame, containerAnimatedStyle]}>
        <Image
          source={require('@/assets/images/logo.png')}
          style={{
            width: dimensions.logoSize,
            height: dimensions.logoSize,
          }}
          resizeMode="contain"
          accessibilityLabel="RegiManager"
        />
      </Animated.View>

      {showText && (
        <Animated.View style={[styles.textWrap, textAnimatedStyle]}>
          <Text style={[styles.brandTitle, { fontSize: dimensions.titleSize, color: brandTextColor }]}>
            REGIMANAGER
          </Text>
          <Text style={[styles.brandSubtitle, { fontSize: dimensions.subtitleSize }]}>Wallet</Text>
          {showTagline && (
            <Text style={styles.brandTagline}>Agent-Linked Mobile Services</Text>
          )}
        </Animated.View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  outerWrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoFrame: {
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#0B1F33',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.28,
    shadowRadius: 12,
    elevation: 6,
  },
  textWrap: {
    alignItems: 'center',
    marginTop: 12,
  },
  brandTitle: {
    fontWeight: '800',
    letterSpacing: -0.5,
    textAlign: 'center',
  },
  brandSubtitle: {
    fontWeight: '800',
    color: Colors.gold,
    marginTop: -2,
    letterSpacing: 0.5,
    textAlign: 'center',
  },
  brandTagline: {
    fontSize: 12,
    fontWeight: '600',
    color: '#94A3B8',
    marginTop: 4,
    letterSpacing: 0.5,
  },
});
