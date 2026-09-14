import React, { useRef, useState } from 'react';
import {
  Dimensions,
  FlatList,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { useRouter } from 'expo-router';

import { AnimatedLogo } from '@/components/AnimatedLogo';
import { Colors } from '@/constants/theme';
import { useAuth } from '@/lib/auth';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

interface Slide {
  id: string;
  icon: string;
  badge: string;
  title: string;
  description: string;
  highlights: string[];
}

const SLIDES: Slide[] = [
  {
    id: 'slide-1',
    icon: '🛡️',
    badge: 'WELCOME TO REGIMANAGER',
    title: 'Agent-Linked Mobile Wallet',
    description:
      'Manage all your insurance policies, DMV vehicle records, and official documents in one secure, agent-connected mobile app.',
    highlights: ['Instant Policy Verification', 'DMV Registration Sync', 'Agent-Direct Connectivity'],
  },
  {
    id: 'slide-2',
    icon: '🎴',
    badge: 'DIGITAL IDENTITY VAULT',
    title: 'Instant Proof & ID Cards',
    description:
      'Access verified proof of insurance cards, vehicle titles, and payment receipts anytime — formatted for official law enforcement inspection.',
    highlights: ['Official Insurance Badges', 'Offline ID Access', 'One-Tap Document Open'],
  },
  {
    id: 'slide-3',
    icon: '🔔',
    badge: 'SMART NOTIFICATIONS & CHAT',
    title: 'Stay Covered & Connected',
    description:
      'Never miss a payment schedule or policy renewal. Receive real-time alerts and message your dedicated insurance broker directly.',
    highlights: ['Payment Due Alerts', 'Vehicle Renewal Tracker', 'Direct Agent Messaging'],
  },
];

export default function OnboardingScreen() {
  const router = useRouter();
  const { markOnboardingComplete } = useAuth();
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatListRef = useRef<FlatList>(null);

  // Reanimated slide indicator width
  const progressWidth = useSharedValue((1 / SLIDES.length) * 100);

  const handleScroll = (event: any) => {
    const offsetX = event.nativeEvent.contentOffset.x;
    const index = Math.round(offsetX / SCREEN_WIDTH);
    if (index !== currentIndex && index >= 0 && index < SLIDES.length) {
      setCurrentIndex(index);
      progressWidth.value = withSpring(((index + 1) / SLIDES.length) * 100);
    }
  };

  const handleNext = async () => {
    if (currentIndex < SLIDES.length - 1) {
      const nextIndex = currentIndex + 1;
      flatListRef.current?.scrollToIndex({ index: nextIndex, animated: true });
      setCurrentIndex(nextIndex);
      progressWidth.value = withSpring(((nextIndex + 1) / SLIDES.length) * 100);
    } else {
      await finishOnboarding();
    }
  };

  const finishOnboarding = async () => {
    await markOnboardingComplete();
    router.replace('/login');
  };

  const progressBarStyle = useAnimatedStyle(() => ({
    width: `${progressWidth.value}%`,
  }));

  const renderSlide = ({ item, index }: { item: Slide; index: number }) => {
    return (
      <View style={styles.slideItem}>
        {/* Animated Logo Display on Slide 1 */}
        {index === 0 ? (
          <View style={styles.logoHeroContainer}>
            <AnimatedLogo size="large" animated={true} textColor={Colors.white} />
          </View>
        ) : (
          <View style={styles.iconCircle}>
            <Text style={styles.iconEmoji}>{item.icon}</Text>
          </View>
        )}

        {/* Slide Category Badge */}
        <View style={styles.slideBadgeContainer}>
          <Text style={styles.slideBadgeText}>{item.badge}</Text>
        </View>

        {/* Title & Description */}
        <Text style={styles.slideTitle}>{item.title}</Text>
        <Text style={styles.slideDescription}>{item.description}</Text>

        {/* Highlights Checklist */}
        <View style={styles.highlightsContainer}>
          {item.highlights.map((text, i) => (
            <View key={i} style={styles.highlightPill}>
              <Text style={styles.highlightCheck}>✓</Text>
              <Text style={styles.highlightText}>{text}</Text>
            </View>
          ))}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safeContainer}>
      {/* Top Header Bar with Skip Button */}
      <View style={styles.topHeader}>
        <View style={styles.headerBrandMini}>
          <Text style={styles.headerBrandText}>RegiManager</Text>
        </View>
        <Pressable style={styles.skipButton} onPress={finishOnboarding}>
          <Text style={styles.skipText}>Skip</Text>
        </Pressable>
      </View>

      {/* Progress Line */}
      <View style={styles.progressBarBackground}>
        <Animated.View style={[styles.progressBarFill, progressBarStyle]} />
      </View>

      {/* Horizontal Carousel */}
      <FlatList
        ref={flatListRef}
        data={SLIDES}
        renderItem={renderSlide}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={handleScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.listContainer}
      />

      {/* Footer Navigation Bar */}
      <View style={styles.footerContainer}>
        {/* Pagination Dots */}
        <View style={styles.dotsRow}>
          {SLIDES.map((_, i) => (
            <View
              key={i}
              style={[
                styles.dot,
                i === currentIndex ? styles.activeDot : styles.inactiveDot,
              ]}
            />
          ))}
        </View>

        {/* Action Button */}
        <Pressable
          style={({ pressed }) => [
            styles.nextButton,
            pressed && styles.buttonPressed,
          ]}
          onPress={handleNext}
        >
          <Text style={styles.nextButtonText}>
            {currentIndex === SLIDES.length - 1 ? 'Get Started 🎉' : 'Next Step →'}
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeContainer: {
    flex: 1,
    backgroundColor: Colors.navy,
  },
  topHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 22,
    paddingTop: 12,
    paddingBottom: 8,
  },
  headerBrandMini: {
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 14,
  },
  headerBrandText: {
    color: Colors.white,
    fontWeight: '800',
    fontSize: 13,
    letterSpacing: 0.5,
  },
  skipButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  skipText: {
    color: '#94A3B8',
    fontWeight: '700',
    fontSize: 14,
  },
  progressBarBackground: {
    height: 3,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    width: '100%',
  },
  progressBarFill: {
    height: 3,
    backgroundColor: '#10B981', // Emerald Accent
  },
  listContainer: {
    alignItems: 'center',
  },
  slideItem: {
    width: SCREEN_WIDTH,
    paddingHorizontal: 26,
    paddingTop: 24,
    alignItems: 'center',
  },
  logoHeroContainer: {
    marginBottom: 20,
    marginTop: 10,
  },
  iconCircle: {
    width: 90,
    height: 90,
    borderRadius: 30,
    backgroundColor: '#1E293B',
    borderWidth: 1.5,
    borderColor: '#3B82F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
    marginTop: 14,
    shadowColor: '#3B82F6',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 10,
    elevation: 4,
  },
  iconEmoji: {
    fontSize: 42,
  },
  slideBadgeContainer: {
    backgroundColor: 'rgba(59, 130, 246, 0.15)',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(59, 130, 246, 0.3)',
    marginBottom: 12,
  },
  slideBadgeText: {
    color: '#93C5FD',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
  },
  slideTitle: {
    fontSize: 26,
    fontWeight: '800',
    color: Colors.white,
    textAlign: 'center',
    letterSpacing: -0.5,
    marginBottom: 10,
  },
  slideDescription: {
    fontSize: 15,
    fontWeight: '400',
    color: '#94A3B8',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
  },
  highlightsContainer: {
    width: '100%',
    gap: 10,
  },
  highlightPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1E293B',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  highlightCheck: {
    color: '#10B981',
    fontWeight: '800',
    fontSize: 16,
    marginRight: 10,
  },
  highlightText: {
    color: Colors.white,
    fontWeight: '600',
    fontSize: 14,
  },
  footerContainer: {
    paddingHorizontal: 26,
    paddingBottom: 30,
    paddingTop: 10,
  },
  dotsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    marginBottom: 20,
  },
  dot: {
    height: 8,
    borderRadius: 4,
  },
  activeDot: {
    width: 24,
    backgroundColor: '#3B82F6',
  },
  inactiveDot: {
    width: 8,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
  },
  nextButton: {
    backgroundColor: Colors.primaryMid,
    borderRadius: 16,
    paddingVertical: 17,
    alignItems: 'center',
    shadowColor: Colors.primaryMid,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 4,
  },
  buttonPressed: {
    opacity: 0.9,
    transform: [{ scale: 0.99 }],
  },
  nextButtonText: {
    color: Colors.white,
    fontWeight: '800',
    fontSize: 16,
    letterSpacing: 0.3,
  },
});
