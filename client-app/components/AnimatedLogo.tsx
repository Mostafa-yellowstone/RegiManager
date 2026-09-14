import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
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
  // Animation Shared Values
  const scale = useSharedValue(animated ? 0.3 : 1);
  const opacity = useSharedValue(animated ? 0 : 1);
  const pulse = useSharedValue(1);
  const walletScale = useSharedValue(animated ? 0 : 1);
  const textTranslateY = useSharedValue(animated ? 20 : 0);
  const textOpacity = useSharedValue(animated ? 0 : 1);

  useEffect(() => {
    if (!animated) return;

    // Reset initial values
    scale.value = 0.3;
    opacity.value = 0;
    walletScale.value = 0;
    textTranslateY.value = 20;
    textOpacity.value = 0;

    // 1. Entrance Spring Scale & Fade In
    scale.value = withSpring(1, { damping: 12, stiffness: 100 });
    opacity.value = withTiming(1, { duration: 500 });

    // 2. Inner Wallet Emblem Pop
    walletScale.value = withDelay(
      300,
      withSpring(1, { damping: 8, stiffness: 120 })
    );

    // 3. Text Slide Up & Fade In
    textTranslateY.value = withDelay(
      450,
      withSpring(0, { damping: 14, stiffness: 90 })
    );
    textOpacity.value = withDelay(450, withTiming(1, { duration: 400 }));

    // 4. Continuous Ambient Shield Pulse (Glow Effect)
    pulse.value = withDelay(
      800,
      withRepeat(
        withSequence(
          withTiming(1.06, { duration: 1500, easing: Easing.inOut(Easing.ease) }),
          withTiming(1.0, { duration: 1500, easing: Easing.inOut(Easing.ease) })
        ),
        -1, // Infinite
        true
      )
    );
  }, [animated]);

  // Animated Styles
  const containerAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value * pulse.value }],
    opacity: opacity.value,
  }));

  const walletAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: walletScale.value }],
  }));

  const textAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: textTranslateY.value }],
    opacity: textOpacity.value,
  }));

  // Sizing mappings
  const dimensions = {
    small: { shieldSize: 54, innerWallet: 22, titleSize: 20, subtitleSize: 10 },
    medium: { shieldSize: 84, innerWallet: 34, titleSize: 26, subtitleSize: 13 },
    large: { shieldSize: 110, innerWallet: 44, titleSize: 32, subtitleSize: 15 },
  }[size];

  const brandTextColor = textColor || Colors.white;

  return (
    <View style={styles.outerWrap}>
      {/* Shield Graphic Badge */}
      <Animated.View
        style={[
          styles.shieldOuter,
          {
            width: dimensions.shieldSize,
            height: dimensions.shieldSize * 1.15,
            borderRadius: dimensions.shieldSize * 0.28,
          },
          containerAnimatedStyle,
        ]}
      >
        {/* Outer Green Circuit Ring Accent */}
        <View
          style={[
            styles.circuitRing,
            {
              borderRadius: dimensions.shieldSize * 0.24,
            },
          ]}
        >
          {/* Circuit Nodes (Dots) */}
          <View style={[styles.node, styles.nodeTopLeft]} />
          <View style={[styles.node, styles.nodeTopRight]} />
          <View style={[styles.node, styles.nodeBottomLeft]} />
          <View style={[styles.node, styles.nodeBottomRight]} />

          {/* Inner Shield Surface */}
          <View style={styles.shieldInner}>
            {/* Wallet Icon Emblem */}
            <Animated.View style={[styles.walletBox, walletAnimatedStyle]}>
              <View
                style={[
                  styles.walletBody,
                  {
                    width: dimensions.innerWallet * 1.2,
                    height: dimensions.innerWallet,
                  },
                ]}
              >
                {/* Wallet Clasp / Coin Button */}
                <View style={styles.walletClasp} />
                <View style={styles.walletCardStrip} />
              </View>
            </Animated.View>
          </View>
        </View>
      </Animated.View>

      {/* Typography Text */}
      {showText && (
        <Animated.View style={[styles.textWrap, textAnimatedStyle]}>
          <View style={styles.brandTitleRow}>
            <Text style={[styles.brandTitle, { fontSize: dimensions.titleSize, color: brandTextColor }]}>
              REGIMANAGER
            </Text>
          </View>
          <Text style={[styles.brandSubtitle, { fontSize: dimensions.subtitleSize }]}>
            Wallet
          </Text>
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
  shieldOuter: {
    backgroundColor: '#0F2942',
    borderWidth: 2.5,
    borderColor: '#0D9488', // Emerald Teal Accent
    alignItems: 'center',
    justifyContent: 'center',
    padding: 4,
    shadowColor: '#0D9488',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.35,
    shadowRadius: 12,
    elevation: 8,
  },
  circuitRing: {
    flex: 1,
    width: '100%',
    borderWidth: 1.5,
    borderColor: '#10B981',
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 3,
  },
  node: {
    position: 'absolute',
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#34D399',
  },
  nodeTopLeft: { top: 4, left: 4 },
  nodeTopRight: { top: 4, right: 4 },
  nodeBottomLeft: { bottom: 6, left: 6 },
  nodeBottomRight: { bottom: 6, right: 6 },
  shieldInner: {
    flex: 1,
    width: '100%',
    backgroundColor: '#1A365D',
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.15)',
  },
  walletBox: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  walletBody: {
    backgroundColor: '#2563EB', // Primary Blue
    borderRadius: 8,
    borderWidth: 1.5,
    borderColor: '#60A5FA',
    justifyContent: 'center',
    alignItems: 'flex-end',
    paddingRight: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 3,
  },
  walletClasp: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: '#FBBF24', // Gold Clasp
    borderWidth: 1,
    borderColor: '#FFFFFF',
  },
  walletCardStrip: {
    position: 'absolute',
    top: 3,
    left: 3,
    right: 14,
    height: 2,
    backgroundColor: 'rgba(255, 255, 255, 0.4)',
    borderRadius: 1,
  },
  textWrap: {
    alignItems: 'center',
    marginTop: 12,
  },
  brandTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  brandTitle: {
    fontWeight: '800',
    letterSpacing: -0.5,
    textAlign: 'center',
  },
  brandSubtitle: {
    fontWeight: '800',
    color: '#10B981', // Emerald Green
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
