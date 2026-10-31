import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PulseTabIcon, type TabKey } from '@/components/pulse/PulseTabIcon';
import { Colors, Fonts } from '@/lib/theme';

type Props = {
  state: { index: number; routes: Array<{ key: string; name: string }> };
  descriptors: Record<string, { options: any }>;
  emitter: {
    emit: (options: {
      type: 'tabPress';
      target?: string;
      canPreventDefault: true;
    }) => { defaultPrevented: boolean };
  };
  navigateToTab: (routeKey: string) => void;
};

const LABELS: Record<TabKey, string> = {
  today: 'Today',
  work: 'Work',
  money: 'Money',
  team: 'Team',
  insurance: 'Insurance',
};

function routeToTab(name: string): TabKey {
  if (name === 'index') return 'today';
  if (name === 'sales') return 'work';
  if (name === 'expenses') return 'money';
  if (name === 'staff') return 'team';
  if (name === 'insurance') return 'insurance';
  return 'today';
}

export function PulseTabBar({ state, descriptors, emitter, navigateToTab }: Props) {
  const insets = useSafeAreaInsets();

  const visibleRoutes = state.routes.filter((route) => {
    const options = descriptors[route.key]?.options || {};
    return options.href !== null;
  });

  return (
    <View
      style={{
        paddingBottom: Math.max(insets.bottom, 10),
        paddingTop: 10,
        paddingHorizontal: 10,
        backgroundColor: Colors.white,
        borderTopWidth: 1,
        borderTopColor: Colors.border,
      }}
    >
      <View
        style={{
          flexDirection: 'row',
          gap: 4,
          backgroundColor: Colors.navySoft,
          borderRadius: 18,
          padding: 5,
        }}
      >
        {visibleRoutes.map((route) => {
          const index = state.routes.findIndex((r) => r.key === route.key);
          const focused = state.index === index;
          const tab = routeToTab(route.name);
          const { options } = descriptors[route.key];
          const label = LABELS[tab] || options.title || route.name;
          const compact = visibleRoutes.length >= 5;

          const onPress = () => {
            const event = emitter.emit({
              type: 'tabPress',
              target: route.key,
              canPreventDefault: true,
            });
            if (!focused && !event.defaultPrevented) {
              navigateToTab(route.key);
            }
          };

          return (
            <Pressable
              key={route.key}
              onPress={onPress}
              accessibilityRole="button"
              accessibilityState={focused ? { selected: true } : {}}
              style={{
                flex: 1,
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 14,
                paddingVertical: 8,
                paddingHorizontal: 2,
                backgroundColor: focused ? Colors.white : 'transparent',
                shadowColor: focused ? Colors.navy : 'transparent',
                shadowOpacity: focused ? 0.08 : 0,
                shadowRadius: 8,
                shadowOffset: { width: 0, height: 2 },
                elevation: focused ? 2 : 0,
              }}
            >
              <View style={{ alignItems: 'center', gap: 3 }}>
                <PulseTabIcon name={tab} focused={focused} compact />
                <Text
                  numberOfLines={1}
                  style={{
                    fontFamily: Fonts.bold,
                    fontSize: compact ? 10 : 11,
                    color: focused ? Colors.teal : Colors.muted,
                  }}
                >
                  {label}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
