import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  Text,
  useWindowDimensions,
  View,
  type ListRenderItemInfo,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  Easing,
  Extrapolation,
  SharedValue,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import { PulseLogo } from '@/components/PulseLogo';
import { hapticLight, hapticMedium } from '@/lib/haptics';
import { markOnboardingComplete } from '@/lib/onboarding';
import { Colors } from '@/lib/theme';

type Slide = {
  id: string;
  badge: string;
  title: string;
  body: string;
  points: string[];
  accent: string;
  kind: 'welcome' | 'profit' | 'staff' | 'ops';
};

const SLIDES: Slide[] = [
  {
    id: 'welcome',
    badge: 'RegiManager Pulse',
    title: 'Your business,\nlive on your phone',
    body: 'Pulse is the owner companion for RegiManager — profit, cash flow, staff, and spaces in one calm dashboard.',
    points: ['Same staff login as the web CRM', 'Built for owners & managers', 'Works alongside your agents'],
    accent: Colors.teal,
    kind: 'welcome',
  },
  {
    id: 'profit',
    badge: 'Money pulse',
    title: 'See what you\nactually earned',
    body: 'Track net profit from insurance and DMV, plus bank cash flow from income and expenses — day by day.',
    points: ['Insurance + DMV profit', 'Bank income vs expenses', 'Period compare badges'],
    accent: Colors.gold,
    kind: 'profit',
  },
  {
    id: 'staff',
    badge: 'Team rhythm',
    title: 'Know who showed\nup on time',
    body: 'Attendance follows your Egypt team start (4:00 PM Cairo) while the work day stays New York for US ops.',
    points: ['On-time vs late at a glance', 'Staff strip on home', 'NY work day, Egypt start'],
    accent: Colors.orange,
    kind: 'staff',
  },
  {
    id: 'ops',
    badge: 'Operations',
    title: 'Drill into spaces\n& expenses',
    body: 'Open DMV, insurance, and expense detail without leaving your pocket — then act from the full CRM when needed.',
    points: ['Space-level performance', 'Expense transaction drill-down', 'Daily snapshot alerts'],
    accent: Colors.blue,
    kind: 'ops',
  },
];

function WaveBar({ height, delay, color }: { height: number; delay: number; color: string }) {
  const scaleY = useSharedValue(0.35);

  useEffect(() => {
    scaleY.value = withDelay(
      delay,
      withRepeat(
        withSequence(
          withTiming(height, { duration: 720, easing: Easing.inOut(Easing.ease) }),
          withTiming(Math.max(0.28, height * 0.55), {
            duration: 720,
            easing: Easing.inOut(Easing.ease),
          }),
        ),
        -1,
        true,
      ),
    );
  }, [delay, height, scaleY]);

  const style = useAnimatedStyle(() => ({
    transform: [{ scaleY: scaleY.value }],
  }));

  return (
    <Animated.View
      style={[
        {
          width: 10,
          height: 88,
          borderRadius: 6,
          backgroundColor: color,
          opacity: 0.88,
        },
        style,
      ]}
    />
  );
}

function WaveBars({ color }: { color: string }) {
  const bars = [0.35, 0.55, 0.9, 0.65, 1, 0.7, 0.45, 0.8, 0.5];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8, height: 88 }}>
      {bars.map((h, i) => (
        <WaveBar key={i} height={h} delay={i * 90} color={color} />
      ))}
    </View>
  );
}

function ProfitCards() {
  const y = useSharedValue(20);
  const opacity = useSharedValue(0);

  useEffect(() => {
    y.value = withSpring(0, { damping: 14, stiffness: 90 });
    opacity.value = withTiming(1, { duration: 480 });
  }, [opacity, y]);

  const style = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: y.value }],
  }));

  return (
    <Animated.View style={[{ width: '100%', gap: 10 }, style]}>
      {[
        { label: 'Net profit', value: '+$12.4k', soft: Colors.tealSoft, color: Colors.tealDeep },
        { label: 'Cash flow', value: '+$8.1k', soft: Colors.goldSoft, color: Colors.navy },
      ].map((card) => (
        <View
          key={card.label}
          style={{
            backgroundColor: card.soft,
            borderRadius: 16,
            paddingVertical: 14,
            paddingHorizontal: 16,
            borderWidth: 1,
            borderColor: 'rgba(15,61,76,0.08)',
          }}
        >
          <Text style={{ color: Colors.muted, fontSize: 12, fontWeight: '700' }}>{card.label}</Text>
          <Text style={{ color: card.color, fontSize: 22, fontWeight: '800', marginTop: 4 }}>
            {card.value}
          </Text>
        </View>
      ))}
    </Animated.View>
  );
}

function StaffDots({ color }: { color: string }) {
  return (
    <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
      {['On time', 'On time', 'Late'].map((label, i) => (
        <View key={`${label}-${i}`} style={{ alignItems: 'center', gap: 8 }}>
          <View
            style={{
              width: 52,
              height: 52,
              borderRadius: 26,
              backgroundColor: i === 2 ? Colors.orangeSoft : Colors.tealSoft,
              borderWidth: 2,
              borderColor: i === 2 ? Colors.orange : color,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <View
              style={{
                width: 14,
                height: 14,
                borderRadius: 7,
                backgroundColor: i === 2 ? Colors.orange : color,
              }}
            />
          </View>
          <Text style={{ color: Colors.mutedLight, fontSize: 11, fontWeight: '700' }}>{label}</Text>
        </View>
      ))}
    </View>
  );
}

function OpsBlocks({ color }: { color: string }) {
  return (
    <View style={{ width: '100%', gap: 10 }}>
      <Text style={{ color: 'rgba(255,255,255,0.45)', fontSize: 11, fontWeight: '700' }}>
        Example areas
      </Text>
      {['DMV space', 'Insurance', 'Expenses'].map((label, i) => (
        <View
          key={label}
          style={{
            height: 48,
            borderRadius: 14,
            backgroundColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            borderColor: 'rgba(255,255,255,0.1)',
            paddingHorizontal: 16,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <View
            style={{
              width: 8,
              height: 8,
              borderRadius: 4,
              backgroundColor: i === 0 ? color : 'rgba(255,255,255,0.35)',
            }}
          />
          <Text style={{ color: Colors.white, fontWeight: '700', fontSize: 14 }}>{label}</Text>
        </View>
      ))}
    </View>
  );
}

function SlideArt({ kind, accent }: { kind: Slide['kind']; accent: string }) {
  if (kind === 'welcome') {
    return (
      <View style={{ alignItems: 'center', gap: 18 }}>
        <PulseLogo size="large" showText={false} animated />
        <WaveBars color={accent} />
      </View>
    );
  }
  if (kind === 'profit') return <ProfitCards />;
  if (kind === 'staff') return <StaffDots color={accent} />;
  return <OpsBlocks color={accent} />;
}

function SlidePage({
  item,
  index,
  scrollX,
  screenW,
}: {
  item: Slide;
  index: number;
  scrollX: SharedValue<number>;
  screenW: number;
}) {
  const style = useAnimatedStyle(() => {
    const input = [(index - 1) * screenW, index * screenW, (index + 1) * screenW];
    return {
      opacity: interpolate(scrollX.value, input, [0.4, 1, 0.4], Extrapolation.CLAMP),
      transform: [
        { translateY: interpolate(scrollX.value, input, [22, 0, 22], Extrapolation.CLAMP) },
        { scale: interpolate(scrollX.value, input, [0.95, 1, 0.95], Extrapolation.CLAMP) },
      ],
    };
  });

  return (
    <View style={{ width: screenW, paddingHorizontal: 28 }}>
      <Animated.View style={[{ flex: 1, paddingTop: 8 }, style]}>
        <View
          style={{
            height: 220,
            borderRadius: 28,
            backgroundColor: 'rgba(255,255,255,0.08)',
            borderWidth: 1,
            borderColor: 'rgba(255,255,255,0.12)',
            alignItems: 'center',
            justifyContent: 'center',
            paddingHorizontal: 20,
            marginBottom: 26,
          }}
        >
          <SlideArt kind={item.kind} accent={item.accent} />
        </View>

        <Text
          style={{
            color: item.accent,
            fontSize: 12,
            fontWeight: '800',
            letterSpacing: 1.1,
            textTransform: 'uppercase',
          }}
        >
          {item.badge}
        </Text>
        <Text
          style={{
            marginTop: 10,
            color: Colors.white,
            fontSize: 32,
            lineHeight: 38,
            fontWeight: '800',
            letterSpacing: -0.7,
          }}
        >
          {item.title}
        </Text>
        <Text style={{ marginTop: 12, color: 'rgba(255,255,255,0.72)', fontSize: 15, lineHeight: 22 }}>
          {item.body}
        </Text>
        <View style={{ marginTop: 18, gap: 8 }}>
          {item.points.map((point) => (
            <View key={point} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: item.accent }} />
              <Text style={{ color: 'rgba(255,255,255,0.9)', fontSize: 14, fontWeight: '600' }}>{point}</Text>
            </View>
          ))}
        </View>
      </Animated.View>
    </View>
  );
}

export default function OnboardingScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width: screenW } = useWindowDimensions();
  const listRef = useRef<FlatList<Slide>>(null);
  const [index, setIndex] = useState(0);
  const scrollX = useSharedValue(0);
  const progress = useSharedValue(1 / SLIDES.length);

  const onScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const x = e.nativeEvent.contentOffset.x;
      scrollX.value = x;
      const nextIndex = Math.round(x / Math.max(1, screenW));
      if (nextIndex !== index && nextIndex >= 0 && nextIndex < SLIDES.length) {
        setIndex(nextIndex);
        progress.value = withSpring((nextIndex + 1) / SLIDES.length, {
          damping: 18,
          stiffness: 120,
        });
      }
    },
    [index, progress, screenW, scrollX],
  );

  const finish = useCallback(async () => {
    await hapticMedium();
    await markOnboardingComplete();
    router.replace('/login');
  }, [router]);

  const next = useCallback(async () => {
    await hapticLight();
    if (index >= SLIDES.length - 1) {
      await finish();
      return;
    }
    const nextIndex = index + 1;
    try {
      listRef.current?.scrollToIndex({ index: nextIndex, animated: true });
    } catch {
      listRef.current?.scrollToOffset({ offset: screenW * nextIndex, animated: true });
    }
    setIndex(nextIndex);
    progress.value = withSpring((nextIndex + 1) / SLIDES.length, { damping: 18, stiffness: 120 });
  }, [finish, index, progress, screenW]);

  const progressStyle = useAnimatedStyle(() => ({
    width: `${progress.value * 100}%`,
  }));

  const renderItem = useCallback(
    ({ item, index: i }: ListRenderItemInfo<Slide>) => (
      <SlidePage item={item} index={i} scrollX={scrollX} screenW={screenW} />
    ),
    [scrollX, screenW],
  );

  return (
    <View style={{ flex: 1, backgroundColor: Colors.navy }}>
      <LinearGradient
        colors={['#0F3D4C', '#0B2E3A', '#083344']}
        style={{ flex: 1, paddingTop: insets.top + 8, paddingBottom: insets.bottom + 16 }}
      >
        <View style={{ paddingHorizontal: 24, flexDirection: 'row', justifyContent: 'flex-end' }}>
          <Pressable onPress={finish} hitSlop={12} style={{ paddingVertical: 8, paddingHorizontal: 4 }}>
            <Text style={{ color: 'rgba(255,255,255,0.55)', fontWeight: '700', fontSize: 14 }}>Skip</Text>
          </Pressable>
        </View>

        <FlatList
          ref={listRef}
          data={SLIDES}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          horizontal
          pagingEnabled
          showsHorizontalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
          bounces={false}
          style={{ flex: 1 }}
          getItemLayout={(_, i) => ({ length: screenW, offset: screenW * i, index: i })}
          onScrollToIndexFailed={(info) => {
            listRef.current?.scrollToOffset({
              offset: screenW * info.index,
              animated: true,
            });
          }}
        />

        <View style={{ paddingHorizontal: 28, gap: 18 }}>
          <View
            style={{
              height: 4,
              borderRadius: 999,
              backgroundColor: 'rgba(255,255,255,0.12)',
              overflow: 'hidden',
            }}
          >
            <Animated.View
              style={[{ height: 4, borderRadius: 999, backgroundColor: Colors.teal }, progressStyle]}
            />
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
            <Text style={{ color: 'rgba(255,255,255,0.45)', fontWeight: '700', fontSize: 13 }}>
              {index + 1} / {SLIDES.length}
            </Text>
            <Pressable
              onPress={next}
              style={{
                backgroundColor: Colors.gold,
                paddingHorizontal: 22,
                paddingVertical: 14,
                borderRadius: 14,
                minWidth: 128,
                alignItems: 'center',
              }}
            >
              <Text style={{ color: Colors.navy, fontWeight: '800', fontSize: 15 }}>
                {index === SLIDES.length - 1 ? 'Get started' : 'Continue'}
              </Text>
            </Pressable>
          </View>
        </View>
      </LinearGradient>
    </View>
  );
}
